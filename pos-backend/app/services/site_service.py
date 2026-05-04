"""Business logic for Site CRUD operations."""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    SITE_ACTIVATED,
    SITE_CREATED,
    SITE_SUSPENDED,
    SITE_UPDATED,
)
from app.models.portal_user import PortalUser
from app.models.site import Site
from app.schemas.site import SiteCreate, SiteUpdate
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


async def _get_or_404(db: AsyncSession, site_id: uuid.UUID) -> Site:
    """
    Fetch a Site by ID or raise HTTP 404.

    Args:
        db: Active database session.
        site_id: The UUID of the site to fetch.

    Returns:
        Site: The found site instance.

    Raises:
        HTTPException: 404 if no site with the given ID exists.
    """
    result = await db.execute(select(Site).where(Site.id == site_id))
    site = result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return site


async def list_sites(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
) -> list[Site]:
    """
    Return a paginated list of all sites.

    Args:
        db: Active database session.
        skip: Number of records to skip (offset).
        limit: Maximum number of records to return.

    Returns:
        list[Site]: The requested page of sites.
    """
    result = await db.execute(
        select(Site).order_by(Site.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def get_site(db: AsyncSession, site_id: uuid.UUID) -> Site:
    """
    Fetch a single site by ID.

    Args:
        db: Active database session.
        site_id: The UUID of the site.

    Returns:
        Site: The found site.

    Raises:
        HTTPException: 404 if the site does not exist.
    """
    return await _get_or_404(db, site_id)


async def create_site(
    db: AsyncSession,
    payload: SiteCreate,
    actor: PortalUser,
) -> Site:
    """
    Create a new Site and write an audit log row in the same transaction.

    Args:
        db: Active database session.
        payload: The site creation data (brand_id + name).
        actor: The authenticated portal user performing the action.

    Returns:
        Site: The newly created site.

    Raises:
        HTTPException: 404 if the referenced brand does not exist.
    """
    from app.models.brand import Brand

    brand_result = await db.execute(select(Brand).where(Brand.id == payload.brand_id))
    if brand_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")

    log.info("site.creating", name=payload.name, brand_id=str(payload.brand_id))

    site = Site(id=uuid.uuid4(), brand_id=payload.brand_id, name=payload.name, is_active=True)
    db.add(site)

    await log_action(
        db=db,
        action=SITE_CREATED,
        entity_type="site",
        entity_id=str(site.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"name": site.name, "brand_id": str(site.brand_id), "is_active": True},
    )

    await db.commit()
    await db.refresh(site)
    log.info("site.created", site_id=str(site.id))
    return site


async def update_site(
    db: AsyncSession,
    site_id: uuid.UUID,
    payload: SiteUpdate,
    actor: PortalUser,
) -> Site:
    """
    Update a Site's mutable fields and write an audit log row.

    Args:
        db: Active database session.
        site_id: The UUID of the site to update.
        payload: The fields to update (all optional).
        actor: The authenticated portal user performing the action.

    Returns:
        Site: The updated site.

    Raises:
        HTTPException: 404 if the site does not exist.
    """
    site = await _get_or_404(db, site_id)

    before = {"name": site.name}
    if payload.name is not None:
        site.name = payload.name
    after = {"name": site.name}

    await log_action(
        db=db,
        action=SITE_UPDATED,
        entity_type="site",
        entity_id=str(site.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after,
    )

    await db.commit()
    await db.refresh(site)
    return site


async def suspend_site(
    db: AsyncSession,
    site_id: uuid.UUID,
    actor: PortalUser,
) -> Site:
    """
    Suspend a site (set is_active = False) and write an audit log row.

    Args:
        db: Active database session.
        site_id: The UUID of the site to suspend.
        actor: The authenticated portal user performing the action.

    Returns:
        Site: The suspended site.

    Raises:
        HTTPException: 404 if the site does not exist.
        HTTPException: 409 if the site is already suspended.
    """
    site = await _get_or_404(db, site_id)

    if not site.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Site is already suspended")

    site.is_active = False

    await log_action(
        db=db,
        action=SITE_SUSPENDED,
        entity_type="site",
        entity_id=str(site.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": True},
        after_state={"is_active": False},
    )

    await db.commit()
    await db.refresh(site)
    return site


async def activate_site(
    db: AsyncSession,
    site_id: uuid.UUID,
    actor: PortalUser,
) -> Site:
    """
    Activate a site (set is_active = True) and write an audit log row.

    Args:
        db: Active database session.
        site_id: The UUID of the site to activate.
        actor: The authenticated portal user performing the action.

    Returns:
        Site: The activated site.

    Raises:
        HTTPException: 404 if the site does not exist.
        HTTPException: 409 if the site is already active.
    """
    site = await _get_or_404(db, site_id)

    if site.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Site is already active")

    site.is_active = True

    await log_action(
        db=db,
        action=SITE_ACTIVATED,
        entity_type="site",
        entity_id=str(site.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": False},
        after_state={"is_active": True},
    )

    await db.commit()
    await db.refresh(site)
    return site
