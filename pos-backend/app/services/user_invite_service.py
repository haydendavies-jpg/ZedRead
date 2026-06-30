"""Business logic for POS user invite creation and acceptance.

Invite flow:
  1. POST /invites — portal admin calls create_invite(); a UserInvite row is
     written and an email is sent via Resend.
  2. The invitee clicks the link, which hits POST /invites/accept with the token.
  3. accept_invite() validates the token, creates a User + UserAccessGrant in
     one transaction, marks the invite accepted, and writes two audit rows.

If the Resend API call fails in create_invite(), the DB transaction is rolled
back so no orphaned invite rows are left behind.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import USER_INVITE_ACCEPTED, USER_INVITED
from app.constants.statuses import ActorType
from app.models.access_profile import AccessProfile
from app.models.brand import Brand
from app.models.user import User
from app.models.site import Site
from app.models.user_access_grant import UserAccessGrant
from app.models.user_invite import UserInvite
from app.schemas.user_invite import InviteAcceptRequest, InviteCreateRequest, InviteResponse
from app.services.audit_service import log_action
from app.utils.email import INVITE_EXPIRY_HOURS, send_invite_email
from app.utils.security import hash_password

log = structlog.get_logger(__name__)


async def create_invite(
    db: AsyncSession,
    brand_id: uuid.UUID,
    payload: InviteCreateRequest,
    actor: User,
) -> InviteResponse:
    """
    Create a UserInvite row and send an invitation email via Resend.

    Validates that the site belongs to the same brand as the actor and that
    the access profile belongs to the same brand.  Both checks prevent
    cross-brand data leakage (rule: routes are thin, all logic in services).

    The Resend API call happens after the DB flush but before commit.  If the
    email send fails, the exception propagates and the caller's transaction is
    rolled back — no orphaned invite row is left in the DB.

    Args:
        db: Active database session.
        brand_id: Brand the actor belongs to; used to scope validation.
        payload: Invite creation data (email, site_id, access_profile_id).
        actor: The authenticated POS user sending the invite.

    Returns:
        InviteResponse: The newly created invite row.

    Raises:
        HTTPException: 404 if site or access profile not found within brand.
        HTTPException: 409 if there is already a pending invite for this email+site.
        Exception: Re-raised from Resend SDK on email delivery failure.
    """
    # Validate site belongs to this brand
    site_result = await db.execute(
        select(Site).where(Site.id == payload.site_id, Site.brand_id == brand_id)
    )
    site = site_result.scalar_one_or_none()
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found within this brand",
        )

    # Validate access profile belongs to this brand
    profile_result = await db.execute(
        select(AccessProfile).where(
            AccessProfile.id == payload.access_profile_id,
            AccessProfile.brand_id == brand_id,
            AccessProfile.is_active == True,  # noqa: E712
        )
    )
    access_profile = profile_result.scalar_one_or_none()
    if access_profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access profile not found within this brand",
        )

    # Reject duplicate pending invite for the same email+site
    existing_result = await db.execute(
        select(UserInvite).where(
            UserInvite.email == payload.email,
            UserInvite.site_id == payload.site_id,
            UserInvite.is_accepted == False,  # noqa: E712
            UserInvite.expires_at > datetime.now(UTC),
        )
    )
    if existing_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pending invite already exists for this email and site",
        )

    # Load brand name for the email body
    brand_result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = brand_result.scalar_one_or_none()
    brand_name = brand.name if brand else "your brand"

    # Generate a cryptographically random token — never derived from user data
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=INVITE_EXPIRY_HOURS)

    invite = UserInvite(
        id=uuid.uuid4(),
        brand_id=brand_id,
        site_id=payload.site_id,
        access_profile_id=payload.access_profile_id,
        invited_by_id=actor.id,
        email=payload.email,
        token=token,
        is_accepted=False,
        expires_at=expires_at,
    )
    db.add(invite)
    # Flush so the invite row has an ID before we attempt the email send
    await db.flush()

    await log_action(
        db=db,
        action=USER_INVITED,
        entity_type="user_invite",
        entity_id=str(invite.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "email": payload.email,
            "site_id": str(payload.site_id),
            "access_profile_id": str(payload.access_profile_id),
            "expires_at": expires_at.isoformat(),
        },
    )

    # Send email — if this raises, explicitly rollback and re-raise (rule 14)
    try:
        await send_invite_email(
            to_email=payload.email,
            inviter_name=actor.name,
            brand_name=brand_name,
            site_name=site.name,
            token=token,
        )
    except Exception:
        await db.rollback()
        raise

    await db.commit()
    await db.refresh(invite)
    log.info("user_invite.created", invite_id=str(invite.id), email=payload.email)
    return InviteResponse.model_validate(invite)


async def accept_invite(
    db: AsyncSession,
    payload: InviteAcceptRequest,
) -> User:
    """
    Accept a pending invite: create the User and UserAccessGrant.

    Validates that the token exists, has not been accepted, and has not
    expired. Creates the user and grant in the same transaction as the invite
    acceptance so all three succeed or all roll back.

    Args:
        db: Active database session.
        payload: Accept data (token, name, password).

    Returns:
        User: The newly created POS user.

    Raises:
        HTTPException: 404 if the token is not found.
        HTTPException: 410 if the invite has already been accepted or has expired.
        HTTPException: 409 if a User with this email already exists.
    """
    # Look up the invite by token
    invite_result = await db.execute(
        select(UserInvite).where(UserInvite.token == payload.token)
    )
    invite = invite_result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found",
        )

    if invite.is_accepted:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Invite has already been accepted",
        )

    if datetime.now(UTC) > invite.expires_at:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Invite has expired",
        )

    # Prevent duplicate users if someone calls accept twice in a race
    existing_user_result = await db.execute(
        select(User).where(User.email == invite.email)
    )
    if existing_user_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A POS user with this email already exists",
        )

    # Resolve the invite's brand to populate the new user's required group_id
    invite_brand_result = await db.execute(select(Brand).where(Brand.id == invite.brand_id))
    invite_brand = invite_brand_result.scalar_one_or_none()
    if invite_brand is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite's brand not found",
        )

    # Create the POS user
    user = User(
        id=uuid.uuid4(),
        group_id=invite_brand.group_id,
        brand_id=invite.brand_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        name=f"{payload.first_name} {payload.last_name}",
        email=invite.email,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)

    # Grant access for the site specified in the invite
    grant = UserAccessGrant(
        id=uuid.uuid4(),
        user_id=user.id,
        site_id=invite.site_id,
        access_profile_id=invite.access_profile_id,
        granted_by_id=invite.invited_by_id,
        is_active=True,
    )
    db.add(grant)

    # Mark the invite consumed
    invite.is_accepted = True

    await log_action(
        db=db,
        action=USER_INVITE_ACCEPTED,
        entity_type="user",
        entity_id=str(user.id),
        actor_type=ActorType.USER,
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
        after_state={
            "invite_id": str(invite.id),
            "brand_id": str(invite.brand_id),
            "site_id": str(invite.site_id),
            "access_profile_id": str(invite.access_profile_id),
        },
    )

    await db.commit()
    await db.refresh(user)
    log.info("user_invite.accepted", user_id=str(user.id), email=user.email)
    return user
