"""Business logic for Site CRUD operations."""

import secrets
import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    ACCESS_GRANT_CREATED,
    SITE_ACTIVATED,
    SITE_CREATED,
    SITE_SUSPENDED,
    SITE_UPDATED,
    USER_CREATED,
)
from app.constants.statuses import ActorType, GrantScope, SystemAccessProfile
from app.models.access_profile import AccessProfile
from app.models.superadmin import SuperAdmin
from app.models.site import Site
from app.models.user import User
from app.models.user_access_grant import UserAccessGrant
from app.schemas.site import SiteCreate, SiteUpdate
from app.services.audit_service import log_action
from app.utils.security import hash_password

log = structlog.get_logger(__name__)


async def _create_master_user(db: AsyncSession, site: Site, actor: SuperAdmin) -> User:
    """
    Auto-create the immutable Master User for a newly created site.

    The Master User's display name is the site's name (not a person's name),
    has no independent login path yet (synthetic email/unusable password —
    real credential rules are deferred to the required-field-rules slice in
    ROLE_MODEL.md), and is granted full, fixed access to its site via the
    brand's Master User system access profile with backend_role='admin'
    (always on, per ROLE_MODEL.md — Master User access can't be disabled).

    Args:
        db: Active database session (transaction already open from caller).
        site: The newly created, already-flushed Site.
        actor: The portal admin who created the site (for audit attribution).

    Returns:
        User: The newly created Master User.

    Raises:
        HTTPException: 404 if the brand's Master User access profile is missing
            (should not happen — seeded by seed_system_profiles() at brand creation).
    """
    profile_r = await db.execute(
        select(AccessProfile).where(
            AccessProfile.brand_id == site.brand_id,
            AccessProfile.name == SystemAccessProfile.MASTER.value,
            AccessProfile.is_system == True,  # noqa: E712
        )
    )
    master_profile = profile_r.scalar_one_or_none()
    if master_profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand is missing its Master User access profile",
        )

    # Synthetic, unguessable credentials — Master User has no real login path yet
    master_user = User(
        id=uuid.uuid4(),
        brand_id=site.brand_id,
        name=site.name,
        email=f"master-{site.id}@system.zedread.internal",
        password_hash=hash_password(secrets.token_urlsafe(32)),
        is_active=True,
        is_master_user=True,
    )
    db.add(master_user)
    await db.flush()

    await log_action(
        db=db,
        action=USER_CREATED,
        entity_type="user",
        entity_id=str(master_user.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "name": master_user.name,
            "brand_id": str(master_user.brand_id),
            "is_master_user": True,
            "site_id": str(site.id),
        },
    )

    grant = UserAccessGrant(
        id=uuid.uuid4(),
        user_id=master_user.id,
        scope=GrantScope.SITE,
        site_id=site.id,
        access_profile_id=master_profile.id,
        granted_by_id=None,  # System-created grant
        is_active=True,
        is_default=True,
        backend_role="admin",
    )
    db.add(grant)

    await log_action(
        db=db,
        action=ACCESS_GRANT_CREATED,
        entity_type="user_access_grant",
        entity_id=str(grant.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "user_id": str(master_user.id),
            "scope": GrantScope.SITE,
            "site_id": str(site.id),
            "access_profile_id": str(master_profile.id),
            "auto_created": True,
        },
    )

    log.info("site.master_user.created", site_id=str(site.id), user_id=str(master_user.id))
    return master_user


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
    name: str | None = None,
    brand_id: uuid.UUID | None = None,
    is_active: bool | None = None,
) -> list[Site]:
    """
    Return a paginated list of all sites with optional filters.

    Args:
        db: Active database session.
        skip: Number of records to skip (offset).
        limit: Maximum number of records to return.
        name: Optional substring filter on Site.name (case-insensitive).
        brand_id: Optional exact-match filter on Site.brand_id.
        is_active: Optional exact-match filter on Site.is_active.

    Returns:
        list[Site]: The requested page of sites.
    """
    conditions: list = []
    if name is not None:
        # Case-insensitive partial match using SQL ILIKE
        conditions.append(Site.name.ilike(f"%{name}%"))
    if brand_id is not None:
        conditions.append(Site.brand_id == brand_id)
    if is_active is not None:
        conditions.append(Site.is_active == is_active)

    result = await db.execute(
        select(Site).where(*conditions).order_by(Site.created_at.desc()).offset(skip).limit(limit)
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
    actor: SuperAdmin,
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
    await db.flush()

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

    # Every site gets exactly one immutable Master User, created atomically
    # with the site itself (ROLE_MODEL.md Master User role).
    await _create_master_user(db, site, actor)

    await db.commit()
    await db.refresh(site)
    log.info("site.created", site_id=str(site.id))
    return site


async def update_site(
    db: AsyncSession,
    site_id: uuid.UUID,
    payload: SiteUpdate,
    actor: SuperAdmin,
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
    actor: SuperAdmin,
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
    actor: SuperAdmin,
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
