"""Business logic for Brand CRUD operations.

Creating a brand auto-creates an 'Uncategorised' system category in the same
transaction — this category cannot be deleted and is used as the fallback for
products not assigned to any other category.
"""

import uuid

import structlog
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    ACCESS_GRANT_CREATED,
    BRAND_ACTIVATED,
    BRAND_CREATED,
    BRAND_LOGO_UPDATED,
    BRAND_SUSPENDED,
    BRAND_UPDATED,
    USER_CREATED,
)
from app.constants.statuses import ActorType, GrantScope, SuperAdminRole, SystemAccessProfile
from app.models.access_profile import AccessProfile
from app.models.brand import Brand
from app.models.category import Category
from app.models.group import Group
from app.models.reporting_group import ReportingGroup
from app.models.tax_category import TaxCategory
from app.models.user import User
from app.models.user_access_grant import UserAccessGrant
from app.models.user_pin import UserPIN
from app.schemas.brand import BrandCreate, BrandUpdate
from app.services import branding_service
from app.services.access_profile_service import seed_system_profiles
from app.services.audit_service import log_action
from app.services.branding_service import ResolvedValue
from app.utils.dependencies import ManagementAccess, _actor_from_mgmt
from app.utils.security import hash_password
from app.utils.storage import ALLOWED_LOGO_TYPES, MAX_LOGO_BYTES, extension_for_content_type, upload_image

log = structlog.get_logger(__name__)


async def _create_brand_master_user(
    db: AsyncSession,
    brand: Brand,
    actor: User,
    master_email: str,
    master_password: str,
) -> User:
    """
    Auto-create the immutable Master User for a newly created brand.

    Uses the supplied real credentials so the operator can log in
    immediately. Also seeds a default PIN of "1337" so the master user
    can authenticate at a POS terminal without a separate PIN-set step.

    Args:
        db: Active database session (transaction already open from caller).
        brand: The newly created, already-flushed Brand.
        actor: The portal admin who created the brand (for audit attribution).
        master_email: Real login email for the master user.
        master_password: Real login password for the master user.

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
        email=master_email,
        password_hash=hash_password(master_password),
        is_active=True,
        is_master_user=True,
    )
    db.add(master_user)
    await db.flush()

    # Seed default PIN "1337" so the master user can log in at a terminal immediately
    db.add(UserPIN(user_id=master_user.id, pin_hash=hash_password("1337"), is_pin_reset_required=False))

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


def _scope_to_own_accounts(conditions: list, actor: User) -> None:
    """
    Restrict a Brand query's conditions to groups the actor created, for Reseller Staff.

    Reseller Staff may only see/manage Brands under Groups they personally
    created (ROLE_MODEL.md §5.1); Admin is unrestricted and this is a no-op.

    Args:
        conditions: The list of SQLAlchemy filter conditions to extend in place.
        actor: The authenticated portal admin (User) performing the action.
    """
    if actor.superadmin_role == SuperAdminRole.RESELLER_STAFF.value:
        conditions.append(
            Brand.group_id.in_(select(Group.id).where(Group.created_by_id == actor.id))
        )


async def _get_or_404(db: AsyncSession, brand_id: uuid.UUID, actor: User) -> Brand:
    """
    Fetch a Brand by ID or raise HTTP 404.

    For Reseller Staff, a Brand outside their own accounts is treated as not
    found rather than forbidden, to avoid leaking existence (ROLE_MODEL.md §5.1).

    Args:
        db: Active database session.
        brand_id: The UUID of the brand to fetch.
        actor: The authenticated portal admin (User) performing the action.

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


def _authorize_management(brand_id: uuid.UUID, mgmt: ManagementAccess, *, write: bool) -> None:
    """
    Verify a management-portal caller may access this Brand, for the
    tenant-facing Company Profile page.

    Read access extends to the caller's own Brand scope plus, for a
    Site-scoped caller, their ancestor Brand (needed to display the
    inherited logo/billing-email on the Site profile form). Write access is
    restricted to an exact Brand-scope match — a Site-scoped caller may view
    but never edit their ancestor Brand's profile.

    Args:
        brand_id: The UUID of the brand being accessed.
        mgmt: The authenticated management-portal caller.
        write: True to apply the stricter write-scope check.

    Raises:
        HTTPException: 404 if the brand is outside the caller's scope (matches
            _get_or_404's "treat as not found" convention for out-of-scope IDs).
    """
    if mgmt.scope == "brand" and mgmt.brand and mgmt.brand.id == brand_id:
        return
    if not write and mgmt.scope == "site" and mgmt.brand and mgmt.brand.id == brand_id:
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")


async def _fetch_for_management(db: AsyncSession, brand_id: uuid.UUID, mgmt: ManagementAccess, *, write: bool) -> Brand:
    """
    Fetch a Brand for a management-portal caller, enforcing scope.

    Args:
        db: Active database session.
        brand_id: The UUID of the brand to fetch.
        mgmt: The authenticated management-portal caller.
        write: True to apply the stricter write-scope check.

    Returns:
        Brand: The found brand.

    Raises:
        HTTPException: 404 if the brand is outside the caller's scope, or does not exist.
    """
    _authorize_management(brand_id, mgmt, write=write)
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()
    if brand is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    return brand


async def _resolve_for_write(
    db: AsyncSession, brand_id: uuid.UUID, actor: User | ManagementAccess
) -> tuple[Brand, dict]:
    """
    Fetch a Brand for a write action and resolve its log_action() actor kwargs.

    Args:
        db: Active database session.
        brand_id: The UUID of the brand to fetch.
        actor: The authenticated portal admin (User) or management-portal caller.

    Returns:
        tuple[Brand, dict]: The brand and keyword arguments ready to splat
            into log_action() (actor_id/actor_email/actor_name).

    Raises:
        HTTPException: 404 if the brand is outside the actor's scope.
    """
    if isinstance(actor, User):
        brand = await _get_or_404(db, brand_id, actor)
        return brand, {"actor_id": actor.id, "actor_email": actor.email, "actor_name": actor.name}
    brand = await _fetch_for_management(db, brand_id, actor, write=True)
    return brand, _actor_from_mgmt(actor)


async def list_brands(
    db: AsyncSession,
    actor: User,
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
        actor: The authenticated portal admin (User) performing the action.
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


async def get_brand(db: AsyncSession, brand_id: uuid.UUID, actor: User | ManagementAccess) -> Brand:
    """
    Fetch a single brand by ID, scoped to the actor's own accounts if Reseller
    Staff, or to a management-portal caller's own scope (see _authorize_management).

    Args:
        db: Active database session.
        brand_id: The UUID of the brand.
        actor: The authenticated User or management-portal caller.

    Returns:
        Brand: The found brand.

    Raises:
        HTTPException: 404 if the brand does not exist within the actor's scope.
    """
    if isinstance(actor, User):
        return await _get_or_404(db, brand_id, actor)
    return await _fetch_for_management(db, brand_id, actor, write=False)


async def create_brand(
    db: AsyncSession,
    payload: BrandCreate,
    actor: User,
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
    if actor.superadmin_role == SuperAdminRole.RESELLER_STAFF.value:
        group_conditions.append(Group.created_by_id == actor.id)
    group_result = await db.execute(select(Group).where(*group_conditions))
    if group_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    log.info("brand.creating", name=payload.name, group_id=str(payload.group_id))

    brand = Brand(
        id=uuid.uuid4(),
        group_id=payload.group_id,
        name=payload.name,
        is_active=True,
        timezone=payload.timezone,
        currency=payload.currency,
        country=payload.country,
        tax_id_value=payload.tax_id_value,
        billing_email=payload.billing_email,
    )
    db.add(brand)
    await db.flush()  # Brand must be in DB before Category and AccessProfile FK inserts

    # Auto-create the brand's default reporting group (Stage 16) before the
    # 'Uncategorised' category, which must reference it
    default_reporting_group = ReportingGroup(
        id=uuid.uuid4(),
        brand_id=brand.id,
        name="Default",
        is_default=True,
        is_system=True,
    )
    db.add(default_reporting_group)
    await db.flush()  # Reporting group must be in DB before the category FK insert

    # Auto-create the system 'Uncategorised' category for every new brand
    uncategorised = Category(
        id=uuid.uuid4(),
        brand_id=brand.id,
        reporting_group_id=default_reporting_group.id,
        name="Uncategorised",
        is_system=True,
        is_active=True,
    )
    db.add(uncategorised)

    # Auto-create the two system taxability classes. Rates are NOT stored here —
    # they resolve at sale time from admin tax templates matched to the site's
    # location; these categories only mark products as taxed or tax-free.
    db.add(TaxCategory(id=uuid.uuid4(), brand_id=brand.id, name="Standard", is_active=True, is_system=True, is_tax_free=False))
    db.add(TaxCategory(id=uuid.uuid4(), brand_id=brand.id, name="Tax Free", is_active=True, is_system=True, is_tax_free=True))

    # Seed the 5 system access profiles (Admin, Reporting Only, Manager, Staff, Master User)
    await seed_system_profiles(db, brand.id)
    await db.flush()  # Profiles must be visible to the lookup in _create_brand_master_user (autoflush=False)

    # Every brand gets exactly one immutable Master User, created atomically
    # with the brand itself (ROLE_MODEL.md Master User role, extended to Brand).
    await _create_brand_master_user(db, brand, actor, payload.master_email, payload.master_password)

    await log_action(
        db=db,
        action=BRAND_CREATED,
        entity_type="brand",
        entity_id=str(brand.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "name": brand.name,
            "group_id": str(brand.group_id),
            "is_active": True,
            "timezone": brand.timezone,
            "currency": brand.currency,
            "country": brand.country,
            "tax_id_value": brand.tax_id_value,
            "billing_email": brand.billing_email,
        },
    )

    await db.commit()
    await db.refresh(brand)
    log.info("brand.created", brand_id=str(brand.id))
    return brand


async def update_brand(
    db: AsyncSession,
    brand_id: uuid.UUID,
    payload: BrandUpdate,
    actor: User | ManagementAccess,
) -> Brand:
    """
    Update a Brand's mutable fields and write an audit log row.

    Args:
        db: Active database session.
        brand_id: The UUID of the brand to update.
        payload: The fields to update (all optional).
        actor: The authenticated portal admin (User) or management-portal caller.

    Returns:
        Brand: The updated brand.

    Raises:
        HTTPException: 404 if the brand does not exist within the actor's scope.
    """
    brand, actor_kwargs = await _resolve_for_write(db, brand_id, actor)

    before = {
        "name": brand.name,
        "timezone": brand.timezone,
        "currency": brand.currency,
        "country": brand.country,
        "tax_id_value": brand.tax_id_value,
        "billing_email": brand.billing_email,
    }
    if payload.name is not None:
        brand.name = payload.name
    if payload.timezone is not None:
        brand.timezone = payload.timezone
    if payload.currency is not None:
        brand.currency = payload.currency
    if payload.country is not None:
        brand.country = payload.country
    if payload.tax_id_value is not None:
        brand.tax_id_value = payload.tax_id_value
    if payload.billing_email is not None:
        brand.billing_email = payload.billing_email
    after = {
        "name": brand.name,
        "timezone": brand.timezone,
        "currency": brand.currency,
        "country": brand.country,
        "tax_id_value": brand.tax_id_value,
        "billing_email": brand.billing_email,
    }

    await log_action(
        db=db,
        action=BRAND_UPDATED,
        entity_type="brand",
        entity_id=str(brand.id),
        **actor_kwargs,
        before_state=before,
        after_state=after,
    )

    await db.commit()
    await db.refresh(brand)
    return brand


async def suspend_brand(
    db: AsyncSession,
    brand_id: uuid.UUID,
    actor: User,
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


async def upload_logo(
    db: AsyncSession,
    brand_id: uuid.UUID,
    file: UploadFile,
    actor: User | ManagementAccess,
) -> Brand:
    """
    Upload or replace a Brand's logo and write an audit log row.

    Accepts JPEG, PNG, or WebP images up to 1 MB. Stores the image in
    Supabase Storage and saves the public URL on the brand row.

    Args:
        db: Active database session.
        brand_id: UUID of the brand to attach the logo to.
        file: The uploaded image file.
        actor: The authenticated portal admin (User) or management-portal caller.

    Returns:
        Brand: The brand with updated logo_url.

    Raises:
        HTTPException: 404 if the brand does not exist within the actor's scope.
        HTTPException: 413 if the file exceeds 1 MB.
        HTTPException: 415 if the content type is not an accepted image type.
    """
    brand, actor_kwargs = await _resolve_for_write(db, brand_id, actor)

    contents = await file.read()
    ext = extension_for_content_type(file.content_type or "")
    logo_url = await upload_image(
        bucket="logos",
        path=f"brands/{brand_id}.{ext}",
        content_type=file.content_type or "",
        contents=contents,
        allowed_content_types=ALLOWED_LOGO_TYPES,
        max_bytes=MAX_LOGO_BYTES,
    )

    old_url = brand.logo_url
    brand.logo_url = logo_url

    await log_action(
        db=db,
        action=BRAND_LOGO_UPDATED,
        entity_type="brand",
        entity_id=str(brand.id),
        **actor_kwargs,
        before_state={"logo_url": old_url},
        after_state={"logo_url": logo_url},
    )

    await db.commit()
    await db.refresh(brand)
    log.info("brand.logo.uploaded", brand_id=str(brand.id))
    return brand


async def request_billing_info(
    db: AsyncSession,
    brand_id: uuid.UUID,
    actor: User | ManagementAccess,
) -> ResolvedValue:
    """
    Send a billing-info-request email to the brand's effective billing contact.

    Args:
        db: Active database session.
        brand_id: The UUID of the brand to request billing info for.
        actor: The authenticated portal admin (User) or management-portal caller.

    Returns:
        ResolvedValue: The billing email sent to and which hierarchy level it came from.

    Raises:
        HTTPException: 404 if the brand does not exist within the actor's scope.
        HTTPException: 409 if no billing email is set anywhere in the brand's chain.
    """
    if isinstance(actor, User):
        brand = await _get_or_404(db, brand_id, actor)
    else:
        brand = await _fetch_for_management(db, brand_id, actor, write=True)
    return await branding_service.request_billing_info(db, brand, "brand", actor)


async def activate_brand(
    db: AsyncSession,
    brand_id: uuid.UUID,
    actor: User,
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
