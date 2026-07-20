"""Business logic for creating and managing POS users from the management portal or admin portal."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import AUTH_PASSWORD_RESET_REQUESTED, USER_CREATED
from app.constants.statuses import GrantScope
from app.models.access_profile import AccessProfile
from app.models.brand import Brand
from app.models.site import Site
from app.models.user import User
from app.models.user_access_grant import UserAccessGrant
from app.schemas.access_grant import AccessGrantCreate
from app.schemas.user import ManagedUserCreate
from app.services import access_grant_service
from app.services.audit_service import log_action
from app.utils.dependencies import ManagementAccess
from app.utils.email import PASSWORD_RESET_EXPIRY_HOURS, send_password_reset_email
from app.utils.security import hash_password, normalize_email

log = structlog.get_logger(__name__)


async def find_email_owner(db: AsyncSession, email: str) -> User | None:
    """
    Return an existing User row that already holds this email, if any.

    users.email is non-unique (migration 0031) — the same email may belong to
    several rows (e.g. a Master User at more than one entity, or a tenant row
    plus a separate portal-admin row). Returns the first match, which is all
    the callers here need (linking a new row's sign-in password to whatever
    the email already resolves to). Compares case-insensitively — login and
    every other identity lookup treat email as case-insensitive (see
    auth_service modules), so the same email typed with different casing
    must resolve to the same owner here too.

    Args:
        db: Active session.
        email: The email to look up.

    Returns:
        User | None: The first row owning the email, or None if unregistered.
    """
    normalized = normalize_email(email)
    result = await db.execute(select(User).where(func.lower(User.email) == normalized))
    return result.scalars().first()


async def create_managed_user(
    db: AsyncSession,
    payload: ManagedUserCreate,
    management_access: ManagementAccess | None,
    superadmin: User | None,
) -> tuple[User, UserAccessGrant]:
    """
    Create a new User plus its initial access grant in one step.

    Backs the management portal's Users page "Add User" action — until now,
    a management caller could only grant additional access to an *existing*
    user (found via search); there was no way to onboard a brand-new one
    without going through the portal-admin-only POST /users route. Scope and
    role-ceiling authority are checked *before* the User row is created (the
    same checks create_grant() applies), so a caller outside their authority
    never leaves an orphaned userless row behind.

    Args:
        db: Active session.
        payload: New user's name/credentials plus the initial grant to create.
        management_access: Set for management JWT callers.
        superadmin: Set for portal admin callers.

    Returns:
        tuple[User, UserAccessGrant]: The created user and their initial grant.

    Raises:
        HTTPException: 404 if the target site/brand/profile doesn't exist.
        HTTPException: 403 if the caller lacks authority for the requested
            scope/entity or the target profile outranks their own.
        HTTPException: 409 for email/password conflicts (see create_user()
            in routes/users.py for the same rules applied here).
    """
    # Resolve the target brand from the requested scope, and validate the
    # entity exists, before touching anything else.
    if payload.scope == "site":
        site_r = await db.execute(select(Site).where(Site.id == payload.site_id))
        site = site_r.scalar_one_or_none()
        if site is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
        brand_id = site.brand_id
    else:
        brand_r = await db.execute(select(Brand).where(Brand.id == payload.brand_id))
        brand = brand_r.scalar_one_or_none()
        if brand is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
        brand_id = brand.id

    profile_r = await db.execute(
        select(AccessProfile).where(
            AccessProfile.id == payload.access_profile_id,
            AccessProfile.is_active == True,  # noqa: E712
        )
    )
    access_profile = profile_r.scalar_one_or_none()
    if access_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access profile not found or inactive")
    access_grant_service.assert_not_master_profile(access_profile)

    # Authority checks run before any write — same rules create_grant() uses,
    # so "who can create a grant at this scope/entity" has exactly one
    # definition (ROLE_MODEL.md §2 scope ladder + role ceiling).
    if management_access:
        await access_grant_service.assert_create_authority(
            db, management_access, payload.scope, payload.site_id, payload.brand_id
        )
        access_grant_service.assert_role_ceiling(management_access, access_profile)

    # Emails are case-insensitive for login — normalize before storing/comparing.
    email = normalize_email(payload.email) if payload.email is not None else None

    # Resolve the sign-in password the same way POST /users does: a shared
    # email links to the existing identity's password rather than creating a
    # competing one.
    password_hash: str | None = None
    if email is not None:
        existing_source = await find_email_owner(db, email)
        if existing_source is not None and existing_source.password_hash is not None:
            if payload.password is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This email already has an account — leave the password blank; the new user shares the existing sign-in password.",
                )
            password_hash = existing_source.password_hash
        elif payload.password is not None:
            password_hash = hash_password(payload.password)

    brand_r2 = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = brand_r2.scalar_one()

    user = User(
        group_id=brand.group_id,
        brand_id=brand_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        name=f"{payload.first_name} {payload.last_name}",
        email=email,
        password_hash=password_hash,
    )
    db.add(user)
    await db.flush()  # assigns user.id without ending the transaction

    actor = management_access.user if management_access else superadmin
    assert actor is not None

    await log_action(
        db=db,
        action=USER_CREATED,
        entity_type="user",
        entity_id=str(user.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"name": user.name, "email": user.email, "brand_id": str(brand_id)},
    )

    # create_grant() re-validates (defense in depth) and commits — the User
    # insert above is flushed but uncommitted, so it commits atomically with
    # the grant in the same transaction.
    grant = await access_grant_service.create_grant(
        db=db,
        management_access=management_access,
        superadmin=superadmin,
        payload=AccessGrantCreate(
            user_id=user.id,
            scope=payload.scope,
            site_id=payload.site_id,
            brand_id=payload.brand_id,
            access_profile_id=payload.access_profile_id,
            backend_role=payload.backend_role,
        ),
    )
    return user, grant


async def request_user_password_reset(
    db: AsyncSession,
    user_id: uuid.UUID,
    management_access: ManagementAccess | None,
    superadmin: User | None,
) -> None:
    """
    Generate a password-reset token for a User and email it to their address.

    Admin-triggered from the Users page edit panel — distinct from the public
    self-service /auth/portal/forgot-password flow (which only covers
    portal-admin accounts today). The emailed link is consumed by the same
    /auth/portal/reset-password endpoint portal-admin resets use.

    Args:
        db: Active session.
        user_id: The target User.
        management_access: Set for management JWT callers.
        superadmin: Set for portal admin callers.

    Raises:
        HTTPException: 404 if the user doesn't exist.
        HTTPException: 403 if the user is outside a management caller's scope.
        HTTPException: 409 if the user has no email on file.
    """
    user_r = await db.execute(select(User).where(User.id == user_id))
    target = user_r.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if management_access is not None:
        if target.brand_id is not None:
            await access_grant_service.assert_brand_readable(db, target.brand_id, management_access)
        else:
            # Group-level Master User — only a group-scope caller in the same group may act.
            in_group = (
                management_access.scope == GrantScope.GROUP
                and management_access.group is not None
                and management_access.group.id == target.group_id
            )
            if not in_group:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is outside your scope")

    if target.email is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User has no email on file — add one before sending a reset link",
        )

    # Cryptographically random — never derived from user data (mirrors portal_auth_service).
    token = secrets.token_urlsafe(32)
    target.password_reset_token = token
    target.password_reset_token_expires_at = datetime.now(UTC) + timedelta(hours=PASSWORD_RESET_EXPIRY_HOURS)

    actor = management_access.user if management_access else superadmin
    assert actor is not None

    await log_action(
        db=db,
        action=AUTH_PASSWORD_RESET_REQUESTED,
        entity_type="user",
        entity_id=str(target.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
    )

    # Send email — if this raises, roll back so no orphaned token is left behind.
    try:
        await send_password_reset_email(to_email=target.email, token=token)
    except Exception:
        await db.rollback()
        raise

    await db.commit()
    log.info("user.password_reset.requested", user_id=str(target.id))
