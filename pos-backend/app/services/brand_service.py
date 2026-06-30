"""Business logic for Brand CRUD operations.

Creating a brand auto-creates an 'Uncategorised' system category in the same
transaction — this category cannot be deleted and is used as the fallback for
products not assigned to any other category.
"""

import secrets
import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    ACCESS_GRANT_CREATED,
    BRAND_ACTIVATED,
    BRAND_CREATED,
    BRAND_SUSPENDED,
    BRAND_UPDATED,
    USER_CREATED,
)
from app.constants.statuses import ActorType, GrantScope, SuperAdminRole, SystemAccessProfile
from app.models.access_profile import AccessProfile
from app.models.brand import Brand
from app.models.category import Category
from app.models.group import Group
from app.models.superadmin import SuperAdmin
from app.models.user import User
from app.models.user_access_grant import UserAccessGrant
from app.schemas.brand import BrandCreate, BrandUpdate
from app.services.access_profile_service import seed_system_profiles
from app.services.audit_service import log_action
from app.utils.security import hash_password

log = structlog.get_logger(__name__)


async def _create_brand_master_user(db: AsyncSession, brand: Brand, actor: SuperAdmin) -> User:
    """
    Auto-create the immutable Master User for a newly created brand.

    Mirrors site_service._create_master_user(): synthetic email/unusable
    password, full fixed access via the brand's seeded Master User access
    profile, backend_role='admin' always on.

    Args:
        db: Active database session (transaction already open from caller).
        brand: The newly created, already-flushed Brand.
        actor: The portal admin who created the brand (for audit attribution).

    Returns:
        User: The newly created Master User.

    Raises:
        HTTPException: 404 if the brand's Master User access profile is missing
            (should not happen — seeded by seed_system_profiles() just before this).
    """
    profile_r = await db.execute(
        select(AccessProfile).where(
            AccessProfile.brand_id == brand.id,
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

    master_user = User(
        id=uuid.uuid4(),
        group_id=brand.group_id,
        brand_id=brand.id,
        name=brand.name,
        email=f"master-{brand.id}@system.zedread.internal",
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
        },
    )

    grant = UserAccessGrant(
        id=uuid.uuid4(),
        user_id=master_user.id,
        scope=GrantScope.BRAND,
        brand_id=brand.id,
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
            "scope": GrantScope.BRAND,
            "brand_id": str(brand.id),
            "access_profile_id": str(master_profile.id),
            "auto_created": True,
        },
    )

    log.info("brand.master_user.created", brand_id=str(brand.id), user_id=str(master_user.id))
    return master_user


def _scope_to_own_accounts(conditions: list, actor: SuperAdmin) -> None:
    """
    Restrict a Brand query's conditions to groups the actor created, for Reseller Staff.

    Reseller Staff may only see/manage Brands under Groups they personally
    created (ROLE_MODEL.md §5.1); Admin is unrestricted and this is a no-op.

    Args:
        conditions: The list of SQLAlchemy filter conditions to extend in place.
        actor: The authenticated SuperAdmin performing the action.
    """
    if actor.role == SuperAdminRole.RESELLER_STAFF.value:
        conditions.append(
            Brand.group_id.in_(select(Group.id).where(Group.created_by_id == actor.id))
        )


async def _get_or_404(db: AsyncSession, brand_id: uuid.UUID, actor: SuperAdmin) -> Brand:
    """
    Fetch a Brand by ID or raise HTTP 404.

    For Reseller Staff, a Brand outside their own accounts is treated as not
    found rather than forbidden, to avoid leaking existence (ROLE_MODEL.md §5.1).

    Args:
        db: Active database session.
        brand_id: The UUID of the brand to fetch.
        actor: The authenticated SuperAdmin performing the action.

    Returns:
        Brand: The found brand instance.

    Raises:
        HTTPException: 404 if no brand with the given ID exists within the actor's scope.
    """
    conditions = [Brand.id == brand_id]
    _scope_to_own_accounts(conditions, actor)
    result = await db.execute(select(Brand).where(*conditions))
    brand = result.scalar_one_or_none()
    if brand is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    return brand


async def list_brands(
    db: AsyncSession,
    actor: SuperAdmin,
    skip: int = 0,
    limit: int = 50,
    name: str | None = None,
    group_id: uuid.UUID | None = None,
    is_active: bool | None = None,
) -> list[Brand]:
    """
    Return a paginated list of brands with optional filters, scoped to the actor's accounts.

    Args:
        db: Active database session.
        actor: The authenticated SuperAdmin performing the action.
        skip: Number of records to skip (offset).
        limit: Maximum number of records to return.
        name: Optional substring filter on Brand.name (case-insensitive).
        group_id: Optional exact-match filter on Brand.group_id.
        is_active: Optional exact-match filter on Brand.is_active.

    Returns:
        list[Brand]: The requested page of brands within the actor's scope.
    """
    conditions: list = []
    if name is not None:
        # Case-insensitive partial match using SQL ILIKE
        conditions.append(Brand.name.ilike(f"%{name}%"))
    if group_id is not None:
        conditions.append(Brand.group_id == group_id)
    if is_active is not None:
        conditions.append(Brand.is_active == is_active)
    _scope_to_own_accounts(conditions, actor)

    result = await db.execute(
        select(Brand).where(*conditions).order_by(Brand.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def get_brand(db: AsyncSession, brand_id: uuid.UUID, actor: SuperAdmin) -> Brand:
    """
    Fetch a single brand by ID, scoped to the actor's own accounts if Reseller Staff.

    Args:
        db: Active database session.
        brand_id: The UUID of the brand.
        actor: The authenticated SuperAdmin performing the action.

    Returns:
        Brand: The found brand.

    Raises:
        HTTPException: 404 if the brand does not exist within the actor's scope.
    """
    return await _get_or_404(db, brand_id, actor)


async def create_brand(
    db: AsyncSession,
    payload: BrandCreate,
    actor: SuperAdmin,
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
        HTTPException: 404 if the referenced group does not exist within the actor's scope.
    """
    # Verify parent group exists, and is within the actor's scope if Reseller Staff
    group_conditions = [Group.id == payload.group_id]
    if actor.role == SuperAdminRole.RESELLER_STAFF.value:
        group_conditions.append(Group.created_by_id == actor.id)
    group_result = await db.execute(select(Group).where(*group_conditions))
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

    # Seed the 5 system access profiles (Admin, Reporting Only, Manager, Staff, Master User)
    await seed_system_profiles(db, brand.id)
    await db.flush()  # Profiles must be visible to the lookup in _create_brand_master_user (autoflush=False)

    # Every brand gets exactly one immutable Master User, created atomically
    # with the brand itself (ROLE_MODEL.md Master User role, extended to Brand).
    await _create_brand_master_user(db, brand, actor)

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
    actor: SuperAdmin,
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
    brand = await _get_or_404(db, brand_id, actor)

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
    actor: SuperAdmin,
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
    brand = await _get_or_404(db, brand_id, actor)

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
    actor: SuperAdmin,
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
    brand = await _get_or_404(db, brand_id, actor)

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
