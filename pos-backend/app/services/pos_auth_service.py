"""Business logic for POS terminal authentication: login, logout, PIN set, and PIN verify."""

import os
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    POS_LOGIN_FAILED,
    POS_LOGIN_SUCCESS,
    POS_LOGOUT,
    POS_PIN_SET,
    POS_PIN_VERIFIED,
)
from app.constants.statuses import ActorType
from app.models.access_profile import AccessProfile
from app.models.user import User
from app.models.site import Site
from app.models.user_access_grant import UserAccessGrant
from app.models.user_pin import UserPIN
from app.models.user_pos_session import UserPOSSession
from app.schemas.pos_auth import (
    PINSetRequest,
    PINVerifyRequest,
    PINVerifyResponse,
    POSLoginRequest,
    POSLoginResponse,
)
from app.services.audit_service import log_action
from app.utils.rate_limit import check_rate_limit
from app.utils.security import (
    create_pos_access_token,
    hash_password,
    normalize_email,
    verify_password_async,
)

log = structlog.get_logger(__name__)

# Login/PIN throttle: at most N attempts per account per window. PINs are only
# 4–6 digits, so throttling per-account is the main brute-force defence (S3).
_LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_RATE_LIMIT", "10"))
_LOGIN_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_WINDOW_SECONDS", "300"))
_PIN_MAX_ATTEMPTS = int(os.getenv("PIN_RATE_LIMIT", "10"))
_PIN_WINDOW_SECONDS = int(os.getenv("PIN_RATE_WINDOW_SECONDS", "300"))


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """
    Fetch a POS user by email address, case-insensitively.

    Args:
        db: Active database session.
        email: The email address to look up.

    Returns:
        User | None: The matching user, or None if not found.
    """
    result = await db.execute(select(User).where(func.lower(User.email) == normalize_email(email)))
    return result.scalar_one_or_none()


async def _get_active_grant_with_profile(
    db: AsyncSession,
    user_id: uuid.UUID,
    site_id: uuid.UUID,
) -> tuple[UserAccessGrant, AccessProfile] | None:
    """
    Fetch the active UserAccessGrant and its AccessProfile for a user+site pair.

    Args:
        db: Active database session.
        user_id: The POS user UUID.
        site_id: The site UUID.

    Returns:
        Tuple of (grant, profile) if an active grant exists, otherwise None.
    """
    grant_result = await db.execute(
        select(UserAccessGrant).where(
            UserAccessGrant.user_id == user_id,
            UserAccessGrant.site_id == site_id,
            UserAccessGrant.is_active == True,  # noqa: E712
        )
    )
    grant = grant_result.scalar_one_or_none()
    if grant is None:
        return None

    profile_result = await db.execute(
        select(AccessProfile).where(AccessProfile.id == grant.access_profile_id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        return None

    return grant, profile


async def login(db: AsyncSession, payload: POSLoginRequest) -> POSLoginResponse:
    """
    Authenticate a POS user with email+password for a specific site.

    Validates credentials, checks that the user has an active grant for the
    requested site, creates a session row, and issues a POS access JWT.

    Writes an audit log row on both success and failure. The failure message
    is intentionally vague to avoid leaking whether the email or site exists.

    Args:
        db: Active database session.
        payload: Login credentials (email, password, site_id).

    Returns:
        POSLoginResponse: Access token, user info, site info, and profile name.

    Raises:
        HTTPException: 401 if credentials are invalid, user is inactive,
                       the site does not exist, or the user has no grant.
    """
    log.info("pos_auth.login.attempt", email=payload.email, site_id=str(payload.site_id))

    # Throttle repeated login attempts against a single account (review S3)
    check_rate_limit(
        f"pos_login:{payload.email.lower()}",
        max_attempts=_LOGIN_MAX_ATTEMPTS,
        window_seconds=_LOGIN_WINDOW_SECONDS,
    )

    user = await _get_user_by_email(db, payload.email)

    # Check all conditions before deciding to avoid timing attacks that could
    # reveal whether an email exists in the system
    credentials_valid = (
        user is not None
        and await verify_password_async(payload.password, user.password_hash)
        and user.is_active
    )

    if not credentials_valid:
        entity_id = str(user.id) if user else payload.email
        await log_action(
            db=db,
            action=POS_LOGIN_FAILED,
            entity_type="user",
            entity_id=entity_id,
            actor_type=ActorType.USER,
            actor_id=None,
            actor_email=payload.email,
            actor_name=None,
            after_state={"site_id": str(payload.site_id), "reason": "invalid_credentials"},
        )
        await db.commit()
        log.warning("pos_auth.login.failed", email=payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify the site exists
    site_result = await db.execute(select(Site).where(Site.id == payload.site_id))
    site = site_result.scalar_one_or_none()
    if site is None:
        await log_action(
            db=db,
            action=POS_LOGIN_FAILED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.USER,
            actor_id=user.id,
            actor_email=user.email,
            actor_name=user.name,
            after_state={"site_id": str(payload.site_id), "reason": "site_not_found"},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify the user has an active grant for this site
    grant_and_profile = await _get_active_grant_with_profile(db, user.id, payload.site_id)
    if grant_and_profile is None:
        await log_action(
            db=db,
            action=POS_LOGIN_FAILED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.USER,
            actor_id=user.id,
            actor_email=user.email,
            actor_name=user.name,
            after_state={"site_id": str(payload.site_id), "reason": "no_active_grant"},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active access grant for this site",
        )

    _grant, access_profile = grant_and_profile

    # Determine whether this user has a PIN set and if reset is required
    pin_result = await db.execute(select(UserPIN).where(UserPIN.user_id == user.id))
    pin_record = pin_result.scalar_one_or_none()
    is_pin_reset_required = pin_record.is_pin_reset_required if pin_record else True

    # Create a session row with a fresh jti so the token can be revoked later
    jti = str(uuid.uuid4())
    session = UserPOSSession(
        id=uuid.uuid4(),
        user_id=user.id,
        site_id=payload.site_id,
        token_jti=jti,
    )
    db.add(session)

    access_token = create_pos_access_token(str(user.id), str(payload.site_id), jti)

    await log_action(
        db=db,
        action=POS_LOGIN_SUCCESS,
        entity_type="user",
        entity_id=str(user.id),
        actor_type=ActorType.USER,
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
        after_state={
            "site_id": str(payload.site_id),
            "access_profile": access_profile.name,
            "session_jti": jti,
        },
    )
    await db.commit()

    log.info("pos_auth.login.success", user_id=str(user.id), site_id=str(payload.site_id))
    return POSLoginResponse(
        access_token=access_token,
        user_id=user.id,
        user_name=user.name,
        site_id=payload.site_id,
        site_name=site.name,
        access_profile_name=access_profile.name,
        is_pin_reset_required=is_pin_reset_required,
    )


async def logout(db: AsyncSession, user: User, jti: str) -> None:
    """
    End the POS session identified by the token's jti, revoking that token.

    Sets ``ended_at`` on the matching ``user_pos_sessions`` row so
    resolve_access() rejects the token on its next use. Idempotent: if the
    session is already ended (or unknown), the call still succeeds so a
    double-logout from the terminal is not an error.

    Args:
        db: Active database session.
        user: The authenticated POS user (from resolve_access).
        jti: The ``jti`` claim of the token being logged out.

    Returns:
        None
    """
    log.info("pos_auth.logout", user_id=str(user.id))

    # Find the still-active session for this token
    session_result = await db.execute(
        select(UserPOSSession).where(
            UserPOSSession.token_jti == jti,
            UserPOSSession.ended_at.is_(None),  # only an active session can be ended
        )
    )
    session = session_result.scalar_one_or_none()

    if session is not None:
        # Mark the session ended — this is what revokes the token going forward
        session.ended_at = datetime.now(UTC)

    await log_action(
        db=db,
        action=POS_LOGOUT,
        entity_type="user",
        entity_id=str(user.id),
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
        after_state={"session_jti": jti},
    )
    await db.commit()
    log.info("pos_auth.logout.complete", user_id=str(user.id))


async def set_pin(
    db: AsyncSession,
    user: User,
    payload: PINSetRequest,
) -> None:
    """
    Set or replace the PIN for the authenticated POS user.

    Upserts the user_pins row — creates on first call, updates on subsequent
    calls. Clears is_pin_reset_required on success so the terminal stops
    prompting for a new PIN.

    Args:
        db: Active database session.
        user: The authenticated POS user (from resolve_access dependency).
        payload: The new PIN (4–6 digits, validated by Pydantic).

    Returns:
        None
    """
    log.info("pos_auth.pin.set", user_id=str(user.id))

    pin_hash = hash_password(payload.pin)

    # Upsert: update existing row or create new one
    existing_result = await db.execute(select(UserPIN).where(UserPIN.user_id == user.id))
    existing = existing_result.scalar_one_or_none()

    if existing is not None:
        existing.pin_hash = pin_hash
        existing.is_pin_reset_required = False
    else:
        pin_record = UserPIN(
            id=uuid.uuid4(),
            user_id=user.id,
            pin_hash=pin_hash,
            is_pin_reset_required=False,
        )
        db.add(pin_record)

    await log_action(
        db=db,
        action=POS_PIN_SET,
        entity_type="user",
        entity_id=str(user.id),
        actor_type=ActorType.USER,
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
    )
    await db.commit()
    log.info("pos_auth.pin.set.complete", user_id=str(user.id))


async def verify_pin(
    db: AsyncSession,
    payload: PINVerifyRequest,
) -> PINVerifyResponse:
    """
    Verify a POS user's PIN and issue a new access token for terminal switch-user.

    Used when a different staff member wants to take over an active terminal
    session without a full email+password login. The outgoing user's session
    remains in the DB (ended_at is not set — the terminal manages that via
    the logout route added in Stage 7.4).

    Writes an audit log row on both success and failure.

    Args:
        db: Active database session.
        payload: Email, PIN, and site_id of the incoming user.

    Returns:
        PINVerifyResponse: Fresh access token, user info, and profile name.

    Raises:
        HTTPException: 401 if the PIN is wrong or the user/grant does not exist.
    """
    log.info("pos_auth.pin.verify.attempt", email=payload.email, site_id=str(payload.site_id))

    # Throttle PIN guessing against a single account — PINs are only 4–6 digits
    check_rate_limit(
        f"pos_pin:{payload.email.lower()}",
        max_attempts=_PIN_MAX_ATTEMPTS,
        window_seconds=_PIN_WINDOW_SECONDS,
    )

    user = await _get_user_by_email(db, payload.email)

    # Load the PIN record — no PIN set means verification cannot succeed
    pin_record: UserPIN | None = None
    if user is not None:
        pin_result = await db.execute(select(UserPIN).where(UserPIN.user_id == user.id))
        pin_record = pin_result.scalar_one_or_none()

    pin_valid = (
        user is not None
        and user.is_active
        and pin_record is not None
        and await verify_password_async(payload.pin, pin_record.pin_hash)
    )

    if not pin_valid:
        entity_id = str(user.id) if user else payload.email
        await log_action(
            db=db,
            action=POS_LOGIN_FAILED,
            entity_type="user",
            entity_id=entity_id,
            actor_type=ActorType.USER,
            actor_id=None,
            actor_email=payload.email,
            actor_name=None,
            after_state={"site_id": str(payload.site_id), "reason": "invalid_pin"},
        )
        await db.commit()
        log.warning("pos_auth.pin.verify.failed", email=payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid PIN",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify active grant for this site
    grant_and_profile = await _get_active_grant_with_profile(db, user.id, payload.site_id)
    if grant_and_profile is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active access grant for this site",
        )

    _grant, access_profile = grant_and_profile

    # Create a new session row for the incoming user's switch-user token
    jti = str(uuid.uuid4())
    session = UserPOSSession(
        id=uuid.uuid4(),
        user_id=user.id,
        site_id=payload.site_id,
        token_jti=jti,
    )
    db.add(session)

    access_token = create_pos_access_token(str(user.id), str(payload.site_id), jti)

    await log_action(
        db=db,
        action=POS_PIN_VERIFIED,
        entity_type="user",
        entity_id=str(user.id),
        actor_type=ActorType.USER,
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
        after_state={
            "site_id": str(payload.site_id),
            "access_profile": access_profile.name,
            "session_jti": jti,
        },
    )
    await db.commit()

    log.info("pos_auth.pin.verify.success", user_id=str(user.id), site_id=str(payload.site_id))
    return PINVerifyResponse(
        access_token=access_token,
        user_id=user.id,
        user_name=user.name,
        access_profile_name=access_profile.name,
        is_pin_reset_required=pin_record.is_pin_reset_required,
    )
