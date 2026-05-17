"""Business logic for Brand CRUD operations.

Creating a brand auto-creates an 'Uncategorised' system category in the same
transaction — this category cannot be deleted and is used as the fallback for
products not assigned to any other category.
"""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    BRAND_ACTIVATED,
    BRAND_CREATED,
    BRAND_SUSPENDED,
    BRAND_UPDATED,
)
from app.models.brand import Brand
from app.models.category import Category
from app.models.portal_user import PortalUser
from app.schemas.brand import BrandCreate, BrandUpdate
from app.services.access_profile_service import seed_system_profiles
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


async def _get_or_404(db: AsyncSession, brand_id: uuid.UUID) -> Brand:
    """
    Fetch a Brand by ID or raise HTTP 404.

    Args:
        db: Active database session.
        brand_id: The UUID of the brand to fetch.

    Returns:
        Brand: The found brand instance.

    Raises:
        HTTPException: 404 if no brand with the given ID exists.
    """
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()
    if brand is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    return brand


async def list_brands(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    name: str | None = None,
    group_id: uuid.UUID | None = None,
    is_active: bool | None = None,
) -> list[Brand]:
    """
    Return a paginated list of all brands with optional filters.

    Args:
        db: Active database session.
        skip: Number of records to skip (offset).
        limit: Maximum number of records to return.
        name: Optional substring filter on Brand.name (case-insensitive).
        group_id: Optional exact-match filter on Brand.group_id.
        is_active: Optional exact-match filter on Brand.is_active.

    Returns:
        list[Brand]: The requested page of brands.
    """
    conditions: list = []
    if name is not None:
        # Case-insensitive partial match using SQL ILIKE
        conditions.append(Brand.name.ilike(f"%{name}%"))
    if group_id is not None:
        conditions.append(Brand.group_id == group_id)
    if is_active is not None:
        conditions.append(Brand.is_active == is_active)

    result = await db.execute(
        select(Brand).where(*conditions).order_by(Brand.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def get_brand(db: AsyncSession, brand_id: uuid.UUID) -> Brand:
    """
    Fetch a single brand by ID.

    Args:
        db: Active database session.
        brand_id: The UUID of the brand.

    Returns:
        Brand: The found brand.

    Raises:
        HTTPException: 404 if the brand does not exist.
    """
    return await _get_or_404(db, brand_id)


async def create_brand(
    db: AsyncSession,
    payload: BrandCreate,
    actor: PortalUser,
) -> Brand:
    """
    Create a Brand and auto-create its 'Uncategorised' system category.

    Both the brand, the category, and the audit log row are committed in a
    single transaction — all succeed or all roll back.

    Args:
        db: Active database session.
        payload: The brand creation data (group_id + name).
        actor: The authenticated portal user performing the action.

    Returns:
        Brand: The newly created brand.

    Raises:
        HTTPException: 404 if the referenced group does not exist.
    """
    from app.models.group import Group

    # Verify parent group exists before creating the brand
    group_result = await db.execute(select(Group).where(Group.id == payload.group_id))
    if group_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    log.info("brand.creating", name=payload.name, group_id=str(payload.group_id))

    brand = Brand(id=uuid.uuid4(), group_id=payload.group_id, name=payload.name, is_active=True)
    db.add(brand)
    await db.flush()  # Brand must be in DB before Category and AccessProfile FK inserts

    # Auto-create the system 'Uncategorised' category for every new brand
    uncategorised = Category(
        id=uuid.uuid4(),
        brand_id=brand.id,
        name="Uncategorised",
        is_system=True,
        is_active=True,
    )
    db.add(uncategorised)

    # Seed the 4 system access profiles (Manager, Supervisor, Cashier, Kitchen)
    await seed_system_profiles(db, brand.id)

    await log_action(
        db=db,
        action=BRAND_CREATED,
        entity_type="brand",
        entity_id=str(brand.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"name": brand.name, "group_id": str(brand.group_id), "is_active": True},
    )

    await db.commit()
    await db.refresh(brand)
    log.info("brand.created", brand_id=str(brand.id))
    return brand


async def update_brand(
    db: AsyncSession,
    brand_id: uuid.UUID,
    payload: BrandUpdate,
    actor: PortalUser,
) -> Brand:
    """
    Update a Brand's mutable fields and write an audit log row.

    Args:
        db: Active database session.
        brand_id: The UUID of the brand to update.
        payload: The fields to update (all optional).
        actor: The authenticated portal user performing the action.

    Returns:
        Brand: The updated brand.

    Raises:
        HTTPException: 404 if the brand does not exist.
    """
    brand = await _get_or_404(db, brand_id)

    before = {"name": brand.name}
    if payload.name is not None:
        brand.name = payload.name
    after = {"name": brand.name}

    await log_action(
        db=db,
        action=BRAND_UPDATED,
        entity_type="brand",
        entity_id=str(brand.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after,
    )

    await db.commit()
    await db.refresh(brand)
    return brand


async def suspend_brand(
    db: AsyncSession,
    brand_id: uuid.UUID,
    actor: PortalUser,
) -> Brand:
    """
    Suspend a brand (set is_active = False) and write an audit log row.

    Args:
        db: Active database session.
        brand_id: The UUID of the brand to suspend.
        actor: The authenticated portal user performing the action.

    Returns:
        Brand: The suspended brand.

    Raises:
        HTTPException: 404 if the brand does not exist.
        HTTPException: 409 if the brand is already suspended.
    """
    brand = await _get_or_404(db, brand_id)

    if not brand.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Brand is already suspended")

    brand.is_active = False

    await log_action(
        db=db,
        action=BRAND_SUSPENDED,
        entity_type="brand",
        entity_id=str(brand.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": True},
        after_state={"is_active": False},
    )

    await db.commit()
    await db.refresh(brand)
    return brand


async def activate_brand(
    db: AsyncSession,
    brand_id: uuid.UUID,
    actor: PortalUser,
) -> Brand:
    """
    Activate a brand (set is_active = True) and write an audit log row.

    Args:
        db: Active database session.
        brand_id: The UUID of the brand to activate.
        actor: The authenticated portal user performing the action.

    Returns:
        Brand: The activated brand.

    Raises:
        HTTPException: 404 if the brand does not exist.
        HTTPException: 409 if the brand is already active.
    """
    brand = await _get_or_404(db, brand_id)

    if brand.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Brand is already active")

    brand.is_active = True

    await log_action(
        db=db,
        action=BRAND_ACTIVATED,
        entity_type="brand",
        entity_id=str(brand.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": False},
        after_state={"is_active": True},
    )

    await db.commit()
    await db.refresh(brand)
    return brand
