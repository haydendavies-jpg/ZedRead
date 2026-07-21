"""Business logic for Site CRUD operations."""

import uuid

import structlog
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    ACCESS_GRANT_CREATED,
    SITE_ACTIVATED,
    SITE_CREATED,
    SITE_LOGO_UPDATED,
    SITE_SUSPENDED,
    SITE_UPDATED,
    USER_CREATED,
)
from app.constants.statuses import ActorType, GrantScope, SuperAdminRole, SystemAccessProfile
from app.models.access_profile import AccessProfile
from app.models.brand import Brand
from app.models.group import Group
from app.models.user import User
from app.models.site import Site
from app.models.user_access_grant import UserAccessGrant
from app.models.user_pin import UserPIN
from app.schemas.site import SiteCreate, SiteUpdate
from app.services import branding_service
from app.services.audit_service import log_action
from app.services.branding_service import ResolvedValue
from app.utils.dependencies import ManagementAccess, _actor_from_mgmt
from app.utils.security import hash_password
from app.utils.storage import ALLOWED_LOGO_TYPES, MAX_LOGO_BYTES, extension_for_content_type, upload_image

log = structlog.get_logger(__name__)


def _scope_to_own_accounts(conditions: list, actor: User) -> None:
    """
    Restrict a Site query's conditions to groups the actor created, for Reseller Staff.

    Reseller Staff may only see/manage Sites under Brands whose Group they
    personally created (ROLE_MODEL.md §5.1); Admin is unrestricted and this
    is a no-op.

    Args:
        conditions: The list of SQLAlchemy filter conditions to extend in place.
        actor: The authenticated portal admin (User) performing the action.
    """
    if actor.superadmin_role == SuperAdminRole.RESELLER_STAFF.value:
        conditions.append(
            Site.brand_id.in_(
                select(Brand.id).where(
                    Brand.group_id.in_(select(Group.id).where(Group.created_by_id == actor.id))
                )
            )
        )


async def _create_master_user(
    db: AsyncSession,
    site: Site,
    actor: User,
    master_email: str,
    master_password: str,
) -> User:
    """
    Auto-create the immutable Master User for a newly created site.

    Uses the supplied real credentials so the operator can log in
    immediately. Also seeds a default PIN of "1337" so the master user
    can authenticate at a POS terminal without a separate PIN-set step.

    Args:
        db: Active database session (transaction already open from caller).
        site: The newly created, already-flushed Site.
        actor: The portal admin who created the site (for audit attribution).
        master_email: Real login email for the master user.
        master_password: Real login password for the master user.

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

    # Site itself has no group_id column — resolve it via its brand
    brand_group_r = await db.execute(select(Brand.group_id).where(Brand.id == site.brand_id))
    brand_group_id = brand_group_r.scalar_one_or_none()
    if brand_group_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site's brand not found")

    master_user = User(
        id=uuid.uuid4(),
        group_id=brand_group_id,
        brand_id=site.brand_id,
        name=site.name,
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


async def _get_or_404(db: AsyncSession, site_id: uuid.UUID, actor: User) -> Site:
    """
    Fetch a Site by ID or raise HTTP 404.

    For Reseller Staff, a Site outside their own accounts is treated as not
    found rather than forbidden, to avoid leaking existence (ROLE_MODEL.md §5.1).

    Args:
        db: Active database session.
        site_id: The UUID of the site to fetch.
        actor: The authenticated portal admin (User) performing the action.

    Returns:
        Site: The found site instance.

    Raises:
        HTTPException: 404 if no site with the given ID exists within the actor's scope.
    """
    conditions = [Site.id == site_id]
    _scope_to_own_accounts(conditions, actor)
    result = await db.execute(select(Site).where(*conditions))
    site = result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return site


def _authorize_management(site_id: uuid.UUID, mgmt: ManagementAccess) -> None:
    """
    Verify a management-portal caller may access this Site, for the
    tenant-facing Company Profile page.

    Site is the leaf of the Group -> Brand -> Site hierarchy, so unlike
    Group/Brand there is no ancestor-read case to allow — a Site-scoped
    caller's own site is both their read and write scope.

    Args:
        site_id: The UUID of the site being accessed.
        mgmt: The authenticated management-portal caller.

    Raises:
        HTTPException: 404 if the site is outside the caller's scope (matches
            _get_or_404's "treat as not found" convention for out-of-scope IDs).
    """
    if mgmt.scope == "site" and mgmt.site and mgmt.site.id == site_id:
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")


async def _fetch_for_management(db: AsyncSession, site_id: uuid.UUID, mgmt: ManagementAccess) -> Site:
    """
    Fetch a Site for a management-portal caller, enforcing scope.

    Args:
        db: Active database session.
        site_id: The UUID of the site to fetch.
        mgmt: The authenticated management-portal caller.

    Returns:
        Site: The found site.

    Raises:
        HTTPException: 404 if the site is outside the caller's scope, or does not exist.
    """
    _authorize_management(site_id, mgmt)
    result = await db.execute(select(Site).where(Site.id == site_id))
    site = result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return site


async def _resolve_for_write(
    db: AsyncSession, site_id: uuid.UUID, actor: User | ManagementAccess
) -> tuple[Site, dict]:
    """
    Fetch a Site for a write action and resolve its log_action() actor kwargs.

    Args:
        db: Active database session.
        site_id: The UUID of the site to fetch.
        actor: The authenticated portal admin (User) or management-portal caller.

    Returns:
        tuple[Site, dict]: The site and keyword arguments ready to splat
            into log_action() (actor_id/actor_email/actor_name).

    Raises:
        HTTPException: 404 if the site is outside the actor's scope.
    """
    if isinstance(actor, User):
        site = await _get_or_404(db, site_id, actor)
        return site, {"actor_id": actor.id, "actor_email": actor.email, "actor_name": actor.name}
    site = await _fetch_for_management(db, site_id, actor)
    return site, _actor_from_mgmt(actor)


async def list_sites(
    db: AsyncSession,
    actor: User,
    skip: int = 0,
    limit: int = 50,
    name: str | None = None,
    brand_id: uuid.UUID | None = None,
    is_active: bool | None = None,
) -> list[Site]:
    """
    Return a paginated list of sites with optional filters, scoped to the actor's accounts.

    Args:
        db: Active database session.
        actor: The authenticated portal admin (User) performing the action.
        skip: Number of records to skip (offset).
        limit: Maximum number of records to return.
        name: Optional substring filter on Site.name (case-insensitive).
        brand_id: Optional exact-match filter on Site.brand_id.
        is_active: Optional exact-match filter on Site.is_active.

    Returns:
        list[Site]: The requested page of sites within the actor's scope.
    """
    conditions: list = []
    if name is not None:
        # Case-insensitive partial match using SQL ILIKE
        conditions.append(Site.name.ilike(f"%{name}%"))
    if brand_id is not None:
        conditions.append(Site.brand_id == brand_id)
    if is_active is not None:
        conditions.append(Site.is_active == is_active)
    _scope_to_own_accounts(conditions, actor)

    result = await db.execute(
        select(Site).where(*conditions).order_by(Site.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def get_site(db: AsyncSession, site_id: uuid.UUID, actor: User | ManagementAccess) -> Site:
    """
    Fetch a single site by ID, scoped to the actor's own accounts if Reseller
    Staff, or to a management-portal caller's own scope (see _authorize_management).

    Args:
        db: Active database session.
        site_id: The UUID of the site.
        actor: The authenticated User or management-portal caller.

    Returns:
        Site: The found site.

    Raises:
        HTTPException: 404 if the site does not exist within the actor's scope.
    """
    if isinstance(actor, User):
        return await _get_or_404(db, site_id, actor)
    return await _fetch_for_management(db, site_id, actor)


async def create_site(
    db: AsyncSession,
    payload: SiteCreate,
    actor: User,
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
        HTTPException: 404 if the referenced brand does not exist within the actor's scope.
    """
    brand_conditions = [Brand.id == payload.brand_id]
    if actor.superadmin_role == SuperAdminRole.RESELLER_STAFF.value:
        brand_conditions.append(
            Brand.group_id.in_(select(Group.id).where(Group.created_by_id == actor.id))
        )
    brand_result = await db.execute(select(Brand).where(*brand_conditions))
    if brand_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")

    log.info("site.creating", name=payload.name, brand_id=str(payload.brand_id))

    site = Site(
        id=uuid.uuid4(),
        brand_id=payload.brand_id,
        name=payload.name,
        is_active=True,
        timezone=payload.timezone,
        currency=payload.currency,
        country=payload.country,
        tax_id_value=payload.tax_id_value,
        billing_email=payload.billing_email,
        address_street=payload.address_street,
        address_state=payload.address_state,
        address_postcode=payload.address_postcode,
    )
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
        after_state={
            "name": site.name,
            "brand_id": str(site.brand_id),
            "is_active": True,
            "timezone": site.timezone,
            "currency": site.currency,
            "country": site.country,
            "tax_id_value": site.tax_id_value,
            "billing_email": site.billing_email,
            "address_street": site.address_street,
            "address_state": site.address_state,
            "address_postcode": site.address_postcode,
        },
    )

    # Every site gets exactly one immutable Master User, created atomically
    # with the site itself (ROLE_MODEL.md Master User role).
    await _create_master_user(db, site, actor, payload.master_email, payload.master_password)

    await db.commit()
    await db.refresh(site)
    log.info("site.created", site_id=str(site.id))
    return site


async def update_site(
    db: AsyncSession,
    site_id: uuid.UUID,
    payload: SiteUpdate,
    actor: User | ManagementAccess,
) -> Site:
    """
    Update a Site's mutable fields and write an audit log row.

    Args:
        db: Active database session.
        site_id: The UUID of the site to update.
        payload: The fields to update (all optional).
        actor: The authenticated portal admin (User) or management-portal caller.

    Returns:
        Site: The updated site.

    Raises:
        HTTPException: 404 if the site does not exist within the actor's scope.
    """
    site, actor_kwargs = await _resolve_for_write(db, site_id, actor)

    before = {
        "name": site.name,
        "timezone": site.timezone,
        "currency": site.currency,
        "country": site.country,
        "tax_id_value": site.tax_id_value,
        "billing_email": site.billing_email,
        "address_street": site.address_street,
        "address_state": site.address_state,
        "address_postcode": site.address_postcode,
    }
    if payload.name is not None:
        site.name = payload.name
    if payload.timezone is not None:
        site.timezone = payload.timezone
    if payload.currency is not None:
        site.currency = payload.currency
    if payload.country is not None:
        site.country = payload.country
    if payload.tax_id_value is not None:
        site.tax_id_value = payload.tax_id_value
    if payload.billing_email is not None:
        site.billing_email = payload.billing_email
    if payload.address_street is not None:
        site.address_street = payload.address_street
    if payload.address_state is not None:
        site.address_state = payload.address_state
    if payload.address_postcode is not None:
        site.address_postcode = payload.address_postcode
    after = {
        "name": site.name,
        "timezone": site.timezone,
        "currency": site.currency,
        "country": site.country,
        "tax_id_value": site.tax_id_value,
        "billing_email": site.billing_email,
        "address_street": site.address_street,
        "address_state": site.address_state,
        "address_postcode": site.address_postcode,
    }

    await log_action(
        db=db,
        action=SITE_UPDATED,
        entity_type="site",
        entity_id=str(site.id),
        **actor_kwargs,
        before_state=before,
        after_state=after,
    )

    await db.commit()
    await db.refresh(site)
    return site


async def suspend_site(
    db: AsyncSession,
    site_id: uuid.UUID,
    actor: User,
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
    site = await _get_or_404(db, site_id, actor)

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


async def upload_logo(
    db: AsyncSession,
    site_id: uuid.UUID,
    file: UploadFile,
    actor: User | ManagementAccess,
) -> Site:
    """
    Upload or replace a Site's logo and write an audit log row.

    Accepts JPEG, PNG, or WebP images up to 1 MB. Stores the image in
    Supabase Storage and saves the public URL on the site row.

    Args:
        db: Active database session.
        site_id: UUID of the site to attach the logo to.
        file: The uploaded image file.
        actor: The authenticated portal admin (User) or management-portal caller.

    Returns:
        Site: The site with updated logo_url.

    Raises:
        HTTPException: 404 if the site does not exist within the actor's scope.
        HTTPException: 413 if the file exceeds 1 MB.
        HTTPException: 415 if the content type is not an accepted image type.
    """
    site, actor_kwargs = await _resolve_for_write(db, site_id, actor)

    contents = await file.read()
    ext = extension_for_content_type(file.content_type or "")
    logo_url = await upload_image(
        bucket="logos",
        path=f"sites/{site_id}.{ext}",
        content_type=file.content_type or "",
        contents=contents,
        allowed_content_types=ALLOWED_LOGO_TYPES,
        max_bytes=MAX_LOGO_BYTES,
    )

    old_url = site.logo_url
    site.logo_url = logo_url

    await log_action(
        db=db,
        action=SITE_LOGO_UPDATED,
        entity_type="site",
        entity_id=str(site.id),
        **actor_kwargs,
        before_state={"logo_url": old_url},
        after_state={"logo_url": logo_url},
    )

    await db.commit()
    await db.refresh(site)
    log.info("site.logo.uploaded", site_id=str(site.id))
    return site


async def request_billing_info(
    db: AsyncSession,
    site_id: uuid.UUID,
    actor: User | ManagementAccess,
) -> ResolvedValue:
    """
    Send a billing-info-request email to the site's effective billing contact.

    Args:
        db: Active database session.
        site_id: The UUID of the site to request billing info for.
        actor: The authenticated portal admin (User) or management-portal caller.

    Returns:
        ResolvedValue: The billing email sent to and which hierarchy level it came from.

    Raises:
        HTTPException: 404 if the site does not exist within the actor's scope.
        HTTPException: 409 if no billing email is set anywhere in the site's chain.
    """
    if isinstance(actor, User):
        site = await _get_or_404(db, site_id, actor)
    else:
        site = await _fetch_for_management(db, site_id, actor)
    return await branding_service.request_billing_info(db, site, "site", actor)


async def activate_site(
    db: AsyncSession,
    site_id: uuid.UUID,
    actor: User,
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
    site = await _get_or_404(db, site_id, actor)

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
