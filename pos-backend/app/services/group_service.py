"""Business logic for Group CRUD operations."""

import uuid

import structlog
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    ACCESS_GRANT_CREATED,
    GROUP_ACTIVATED,
    GROUP_CREATED,
    GROUP_LOGO_UPDATED,
    GROUP_SUSPENDED,
    GROUP_UPDATED,
    USER_CREATED,
)
from app.constants.statuses import ActorType, GrantScope, SuperAdminRole, SystemAccessProfile
from app.models.access_profile import AccessProfile
from app.models.group import Group
from app.models.superadmin import SuperAdmin
from app.models.user import User
from app.models.user_access_grant import UserAccessGrant
from app.models.user_pin import UserPIN
from app.schemas.group import GroupCreate, GroupUpdate
from app.services import branding_service
from app.services.access_profile_service import seed_group_master_profile
from app.services.audit_service import log_action
from app.services.branding_service import ResolvedValue
from app.utils.security import hash_password
from app.utils.storage import ALLOWED_LOGO_TYPES, MAX_LOGO_BYTES, extension_for_content_type, upload_image

log = structlog.get_logger(__name__)


def _scope_to_own_accounts(conditions: list, actor: SuperAdmin) -> None:
    """
    Restrict a query's conditions to groups the actor created, for Reseller Staff.

    Reseller Staff may only see/manage Groups they personally created
    (ROLE_MODEL.md §5.1); Admin is unrestricted and this is a no-op.

    Args:
        conditions: The list of SQLAlchemy filter conditions to extend in place.
        actor: The authenticated SuperAdmin performing the action.
    """
    if actor.role == SuperAdminRole.RESELLER_STAFF.value:
        conditions.append(Group.created_by_id == actor.id)


async def _get_or_404(db: AsyncSession, group_id: uuid.UUID, actor: SuperAdmin) -> Group:
    """
    Fetch a Group by ID or raise HTTP 404.

    For Reseller Staff, a Group outside their own accounts is treated as not
    found rather than forbidden, to avoid leaking the existence of other
    resellers' or ZedRead-direct accounts (ROLE_MODEL.md §5.1).

    Args:
        db: Active database session.
        group_id: The UUID of the group to fetch.
        actor: The authenticated SuperAdmin performing the action.

    Returns:
        Group: The found group instance.

    Raises:
        HTTPException: 404 if no group with the given ID exists within the actor's scope.
    """
    conditions = [Group.id == group_id]
    _scope_to_own_accounts(conditions, actor)
    result = await db.execute(select(Group).where(*conditions))
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return group


async def list_groups(
    db: AsyncSession,
    actor: SuperAdmin,
    skip: int = 0,
    limit: int = 50,
    name: str | None = None,
    is_active: bool | None = None,
) -> list[Group]:
    """
    Return a paginated list of groups with optional filters.

    Reseller Staff only see Groups they personally created; Admin sees all
    Groups (ROLE_MODEL.md §5.1).

    Args:
        db: Active database session.
        actor: The authenticated SuperAdmin performing the action.
        skip: Number of records to skip (offset).
        limit: Maximum number of records to return.
        name: Optional substring filter on Group.name (case-insensitive).
        is_active: Optional exact-match filter on Group.is_active.

    Returns:
        list[Group]: The requested page of groups within the actor's scope.
    """
    conditions: list = []
    if name is not None:
        # Case-insensitive partial match using SQL ILIKE
        conditions.append(Group.name.ilike(f"%{name}%"))
    if is_active is not None:
        conditions.append(Group.is_active == is_active)
    _scope_to_own_accounts(conditions, actor)

    result = await db.execute(
        select(Group).where(*conditions).order_by(Group.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def get_group(db: AsyncSession, group_id: uuid.UUID, actor: SuperAdmin) -> Group:
    """
    Fetch a single group by ID, scoped to the actor's own accounts if Reseller Staff.

    Args:
        db: Active database session.
        group_id: The UUID of the group.
        actor: The authenticated SuperAdmin performing the action.

    Returns:
        Group: The found group.

    Raises:
        HTTPException: 404 if the group does not exist within the actor's scope.
    """
    return await _get_or_404(db, group_id, actor)


async def _create_group_master_user(
    db: AsyncSession,
    group: Group,
    actor: SuperAdmin,
    master_email: str,
    master_password: str,
) -> User:
    """
    Auto-create the immutable Master User for a newly created group.

    Mirrors site_service._create_master_user() and
    brand_service._create_brand_master_user(). Uses the supplied real
    credentials so the operator can log in immediately. A group-level
    Master User has no brand (User.brand_id is NULL) — its scope is the
    whole group. Also seeds a default PIN of "1337" so the master user
    can authenticate at a POS terminal without a separate PIN-set step.

    Args:
        db: Active database session (transaction already open from caller).
        group: The newly created, already-flushed Group.
        actor: The portal admin who created the group (for audit attribution).
        master_email: Real login email for the master user.
        master_password: Real login password for the master user.

    Returns:
        User: The newly created Master User.

    Raises:
        HTTPException: 404 if the group's Master User access profile is missing
            (should not happen — seeded by seed_group_master_profile() just before this).
    """
    profile_r = await db.execute(
        select(AccessProfile).where(
            AccessProfile.group_id == group.id,
            AccessProfile.name == SystemAccessProfile.MASTER.value,
            AccessProfile.is_system == True,  # noqa: E712
        )
    )
    master_profile = profile_r.scalar_one_or_none()
    if master_profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group is missing its Master User access profile",
        )

    master_user = User(
        id=uuid.uuid4(),
        group_id=group.id,
        brand_id=None,
        name=group.name,
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
            "group_id": str(master_user.group_id),
            "is_master_user": True,
        },
    )

    grant = UserAccessGrant(
        id=uuid.uuid4(),
        user_id=master_user.id,
        scope=GrantScope.GROUP,
        group_id=group.id,
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
            "scope": GrantScope.GROUP,
            "group_id": str(group.id),
            "access_profile_id": str(master_profile.id),
            "auto_created": True,
        },
    )

    log.info("group.master_user.created", group_id=str(group.id), user_id=str(master_user.id))
    return master_user


async def create_group(
    db: AsyncSession,
    payload: GroupCreate,
    actor: SuperAdmin,
) -> Group:
    """
    Create a new Group, seed its Master User access profile, auto-create its
    Master User, and write audit log rows — all in the same transaction.

    Args:
        db: Active database session.
        payload: The group creation data.
        actor: The authenticated portal user performing the action.

    Returns:
        Group: The newly created group.
    """
    log.info("group.creating", name=payload.name, actor_id=str(actor.id))

    # Record the creating SuperAdmin so Reseller Staff can be scoped to own accounts
    group = Group(
        id=uuid.uuid4(),
        name=payload.name,
        is_active=True,
        created_by_id=actor.id,
        timezone=payload.timezone,
        currency=payload.currency,
        country=payload.country,
        tax_id_value=payload.tax_id_value,
        billing_email=payload.billing_email,
    )
    db.add(group)
    await db.flush()  # Group must be in DB before AccessProfile/User FK inserts

    await log_action(
        db=db,
        action=GROUP_CREATED,
        entity_type="group",
        entity_id=str(group.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "name": group.name,
            "is_active": group.is_active,
            "timezone": group.timezone,
            "currency": group.currency,
            "country": group.country,
            "tax_id_value": group.tax_id_value,
            "billing_email": group.billing_email,
        },
    )

    # Every group gets exactly one immutable Master User, created atomically
    # with the group itself (ROLE_MODEL.md Master User role, extended to Group).
    await seed_group_master_profile(db, group.id)
    await db.flush()  # Profile must be visible to the lookup in _create_group_master_user (autoflush=False)
    await _create_group_master_user(db, group, actor, payload.master_email, payload.master_password)

    await db.commit()
    await db.refresh(group)
    log.info("group.created", group_id=str(group.id))
    return group


async def update_group(
    db: AsyncSession,
    group_id: uuid.UUID,
    payload: GroupUpdate,
    actor: SuperAdmin,
) -> Group:
    """
    Update a Group's mutable fields and write an audit log row.

    Args:
        db: Active database session.
        group_id: The UUID of the group to update.
        payload: The fields to update (all optional).
        actor: The authenticated portal user performing the action.

    Returns:
        Group: The updated group.

    Raises:
        HTTPException: 404 if the group does not exist within the actor's scope.
    """
    group = await _get_or_404(db, group_id, actor)

    before = {
        "name": group.name,
        "timezone": group.timezone,
        "currency": group.currency,
        "country": group.country,
        "tax_id_value": group.tax_id_value,
        "billing_email": group.billing_email,
    }
    if payload.name is not None:
        group.name = payload.name
    if payload.timezone is not None:
        group.timezone = payload.timezone
    if payload.currency is not None:
        group.currency = payload.currency
    if payload.country is not None:
        group.country = payload.country
    if payload.tax_id_value is not None:
        group.tax_id_value = payload.tax_id_value
    if payload.billing_email is not None:
        group.billing_email = payload.billing_email
    after = {
        "name": group.name,
        "timezone": group.timezone,
        "currency": group.currency,
        "country": group.country,
        "tax_id_value": group.tax_id_value,
        "billing_email": group.billing_email,
    }

    await log_action(
        db=db,
        action=GROUP_UPDATED,
        entity_type="group",
        entity_id=str(group.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after,
    )

    await db.commit()
    await db.refresh(group)
    return group


async def suspend_group(
    db: AsyncSession,
    group_id: uuid.UUID,
    actor: SuperAdmin,
) -> Group:
    """
    Set a Group's is_active flag to False and write an audit log row.

    Args:
        db: Active database session.
        group_id: The UUID of the group to suspend.
        actor: The authenticated portal user performing the action.

    Returns:
        Group: The suspended group.

    Raises:
        HTTPException: 404 if the group does not exist within the actor's scope.
        HTTPException: 409 if the group is already suspended.
    """
    group = await _get_or_404(db, group_id, actor)

    if not group.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group is already suspended")

    group.is_active = False

    await log_action(
        db=db,
        action=GROUP_SUSPENDED,
        entity_type="group",
        entity_id=str(group.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": True},
        after_state={"is_active": False},
    )

    await db.commit()
    await db.refresh(group)
    return group


async def upload_logo(
    db: AsyncSession,
    group_id: uuid.UUID,
    file: UploadFile,
    actor: SuperAdmin,
) -> Group:
    """
    Upload or replace a Group's logo and write an audit log row.

    Accepts JPEG, PNG, or WebP images up to 1 MB. Stores the image in
    Supabase Storage and saves the public URL on the group row.

    Args:
        db: Active database session.
        group_id: UUID of the group to attach the logo to.
        file: The uploaded image file.
        actor: The authenticated portal user performing the action.

    Returns:
        Group: The group with updated logo_url.

    Raises:
        HTTPException: 404 if the group does not exist within the actor's scope.
        HTTPException: 413 if the file exceeds 1 MB.
        HTTPException: 415 if the content type is not an accepted image type.
    """
    group = await _get_or_404(db, group_id, actor)

    contents = await file.read()
    ext = extension_for_content_type(file.content_type or "")
    logo_url = await upload_image(
        bucket="logos",
        path=f"groups/{group_id}.{ext}",
        content_type=file.content_type or "",
        contents=contents,
        allowed_content_types=ALLOWED_LOGO_TYPES,
        max_bytes=MAX_LOGO_BYTES,
    )

    old_url = group.logo_url
    group.logo_url = logo_url

    await log_action(
        db=db,
        action=GROUP_LOGO_UPDATED,
        entity_type="group",
        entity_id=str(group.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"logo_url": old_url},
        after_state={"logo_url": logo_url},
    )

    await db.commit()
    await db.refresh(group)
    log.info("group.logo.uploaded", group_id=str(group.id))
    return group


async def request_billing_info(
    db: AsyncSession,
    group_id: uuid.UUID,
    actor: SuperAdmin,
) -> ResolvedValue:
    """
    Send a billing-info-request email to the group's effective billing contact.

    Args:
        db: Active database session.
        group_id: The UUID of the group to request billing info for.
        actor: The authenticated portal user performing the action.

    Returns:
        ResolvedValue: The billing email sent to and which hierarchy level it came from.

    Raises:
        HTTPException: 404 if the group does not exist within the actor's scope.
        HTTPException: 409 if no billing email is set anywhere in the group's chain.
    """
    group = await _get_or_404(db, group_id, actor)
    return await branding_service.request_billing_info(db, group, "group", actor)


async def activate_group(
    db: AsyncSession,
    group_id: uuid.UUID,
    actor: SuperAdmin,
) -> Group:
    """
    Set a Group's is_active flag to True and write an audit log row.

    Args:
        db: Active database session.
        group_id: The UUID of the group to activate.
        actor: The authenticated portal user performing the action.

    Returns:
        Group: The activated group.

    Raises:
        HTTPException: 404 if the group does not exist within the actor's scope.
        HTTPException: 409 if the group is already active.
    """
    group = await _get_or_404(db, group_id, actor)

    if group.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group is already active")

    group.is_active = True

    await log_action(
        db=db,
        action=GROUP_ACTIVATED,
        entity_type="group",
        entity_id=str(group.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": False},
        after_state={"is_active": True},
    )

    await db.commit()
    await db.refresh(group)
    return group
