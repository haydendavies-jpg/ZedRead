"""Business logic for portal user authentication: login, refresh, and user lookup."""

import structlog
from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import AUTH_LOGIN_FAILED, AUTH_LOGIN_SUCCESS, AUTH_TOKEN_REFRESHED
from app.constants.statuses import ActorType
from app.models.portal_user import PortalUser
from app.schemas.portal_auth import LoginRequest, TokenResponse
from app.services.audit_service import log_action
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)

log = structlog.get_logger(__name__)


async def _get_user_by_email(db: AsyncSession, email: str) -> PortalUser | None:
    """
    Fetch a portal user by email address.

    Args:
        db: The active database session.
        email: The email address to look up.

    Returns:
        PortalUser | None: The matching user, or None if not found.
    """
    result = await db.execute(
        select(PortalUser).where(PortalUser.email == email)
    )
    return result.scalar_one_or_none()


async def login(db: AsyncSession, payload: LoginRequest) -> TokenResponse:
    """
    Authenticate a portal user and return an access + refresh token pair.

    Writes an audit log row on both success and failure.
    On failure, raises HTTP 401 — the error message is intentionally vague
    to avoid leaking whether the email exists (security best practice).

    Args:
        db: The active database session.
        payload: The login credentials (email + password).

    Returns:
        TokenResponse: The access and refresh token pair.

    Raises:
        HTTPException: 401 if credentials are invalid or user is inactive.
    """
    log.info("auth.login.attempt", email=payload.email)

    user = await _get_user_by_email(db, payload.email)

    # Evaluate both conditions before deciding — avoids timing attacks that
    # could reveal whether an email exists in the system
    credentials_valid = (
        user is not None
        and verify_password(payload.password, user.password_hash)
        and user.is_active
    )

    if not credentials_valid:
        # Audit failure — entity_id uses email since we may not have a user ID
        entity_id = str(user.id) if user else payload.email
        await log_action(
            db=db,
            action=AUTH_LOGIN_FAILED,
            entity_type="portal_user",
            entity_id=entity_id,
            actor_type=ActorType.USER,
            actor_id=None,
            actor_email=payload.email,
            actor_name=None,
        )
        await db.commit()
        log.warning("auth.login.failed", email=payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Success — issue tokens and audit the login
    access_token = create_access_token(str(user.id), user.role)
    refresh_token = create_refresh_token(str(user.id))

    await log_action(
        db=db,
        action=AUTH_LOGIN_SUCCESS,
        entity_type="portal_user",
        entity_id=str(user.id),
        actor_type=ActorType.USER,
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
    )
    await db.commit()

    log.info("auth.login.success", user_id=str(user.id), email=user.email)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


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
        select(PortalUser).where(PortalUser.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    new_access = create_access_token(str(user.id), user.role)
    new_refresh = create_refresh_token(str(user.id))

    await log_action(
        db=db,
        action=AUTH_TOKEN_REFRESHED,
        entity_type="portal_user",
        entity_id=str(user.id),
        actor_type=ActorType.USER,
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
    )
    await db.commit()

    log.info("auth.token.refreshed", user_id=str(user.id))
    return TokenResponse(access_token=new_access, refresh_token=new_refresh)
