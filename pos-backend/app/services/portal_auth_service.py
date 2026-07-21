"""Business logic for portal admin authentication: refresh, password reset, and user lookup."""

import secrets
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    AUTH_PASSWORD_RESET_COMPLETED,
    AUTH_PASSWORD_RESET_REQUESTED,
    AUTH_TOKEN_REFRESHED,
)
from app.constants.statuses import ActorType
from app.models.user import User
from app.schemas.portal_auth import TokenResponse
from app.services.audit_service import log_action
from app.utils.email import PASSWORD_RESET_EXPIRY_HOURS, send_password_reset_email
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    normalize_email,
)

log = structlog.get_logger(__name__)


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """
    Fetch a portal admin (User with superadmin_role set) by email, case-insensitively.

    Args:
        db: The active database session.
        email: The email address to look up.

    Returns:
        User | None: The matching portal admin, or None if not found.
    """
    # .scalars().first() rather than .scalar_one_or_none() - users.email is
    # intentionally non-unique (migration 0031/0050), so more than one
    # superadmin_role row can share an email; this only feeds a
    # forgot-password request, where picking any one matching account and
    # emailing its reset link is a safe outcome, not a crash.
    result = await db.execute(
        select(User).where(
            func.lower(User.email) == normalize_email(email),
            User.superadmin_role.isnot(None),
        )
    )
    return result.scalars().first()


async def refresh(db: AsyncSession, refresh_token: str) -> TokenResponse:
    """
    Exchange a valid refresh token for a new access + refresh token pair.

    Re-reads the user's current role from the DB so role changes take effect
    without requiring the user to log out and back in.

    Args:
        db: The active database session.
        refresh_token: The refresh JWT to validate and exchange.

    Returns:
        TokenResponse: A new token pair.

    Raises:
        HTTPException: 401 if the refresh token is invalid, expired, or the user is inactive.
    """
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload.get("sub", "")
    result = await db.execute(
        select(User).where(User.id == user_id, User.superadmin_role.isnot(None))
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reject a refresh token minted before a token_version bump
    if payload.get("tv", 0) != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked — please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )

    new_access = create_access_token(str(user.id), user.superadmin_role, user.token_version)
    new_refresh = create_refresh_token(str(user.id), user.token_version)

    await log_action(
        db=db,
        action=AUTH_TOKEN_REFRESHED,
        entity_type="user",
        entity_id=str(user.id),
        actor_type=ActorType.USER,
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
    )
    await db.commit()

    log.info("auth.token.refreshed", user_id=str(user.id))
    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


async def request_password_reset(db: AsyncSession, email: str) -> None:
    """
    Generate a password reset token and email it to the user, if the account exists.

    Always returns successfully regardless of whether the email matches a
    portal user — this prevents an attacker from using the endpoint to
    enumerate registered email addresses.

    Args:
        db: The active database session.
        email: The email address supplied on the forgot-password form.

    Returns:
        None
    """
    user = await _get_user_by_email(db, email)
    if user is None or not user.is_active:
        log.info("auth.password_reset.requested.unknown_email", email=email)
        return

    # Generate a cryptographically random token — never derived from user data
    token = secrets.token_urlsafe(32)
    user.password_reset_token = token
    user.password_reset_token_expires_at = datetime.now(UTC) + timedelta(
        hours=PASSWORD_RESET_EXPIRY_HOURS
    )

    await log_action(
        db=db,
        action=AUTH_PASSWORD_RESET_REQUESTED,
        entity_type="user",
        entity_id=str(user.id),
        actor_type=ActorType.USER,
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
    )

    # Send email — if this raises, roll back so no orphaned token is left behind
    try:
        await send_password_reset_email(to_email=user.email, token=token)
    except Exception:
        await db.rollback()
        raise

    await db.commit()
    log.info("auth.password_reset.requested", user_id=str(user.id))


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    """
    Consume a password reset token and set the account's new password.

    A single `users` table lookup now serves both the portal self-service
    flow (a row with superadmin_role set) and the admin-triggered reset for
    a tenant row (see user_service.request_user_password_reset()) — reset
    tokens are opaque random strings, not derived from role.

    Args:
        db: The active database session.
        token: The raw reset token from the emailed link.
        new_password: The new plaintext password (validated by the caller).

    Returns:
        None

    Raises:
        HTTPException: 400 if the token is invalid or has expired.
    """
    result = await db.execute(select(User).where(User.password_reset_token == token))
    account = result.scalar_one_or_none()

    if account is None or account.password_reset_token_expires_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    if datetime.now(UTC) > account.password_reset_token_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    account.password_hash = hash_password(new_password)
    # Single-use — clear the token so it cannot be replayed
    account.password_reset_token = None
    account.password_reset_token_expires_at = None
    # Revoke every previously issued token for this account — a reset implies
    # the old credential (and any session riding on it) can no longer be trusted
    account.token_version += 1

    await log_action(
        db=db,
        action=AUTH_PASSWORD_RESET_COMPLETED,
        entity_type="user",
        entity_id=str(account.id),
        actor_type=ActorType.USER,
        actor_id=account.id,
        actor_email=account.email,
        actor_name=account.name,
    )
    await db.commit()
    log.info("auth.password_reset.completed", user_id=str(account.id))
