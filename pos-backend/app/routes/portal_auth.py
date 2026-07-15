"""Portal authentication routes: login, token refresh, management scope selection, and change password."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import AUTH_LOGOUT, AUTH_PASSWORD_CHANGED
from app.database import get_db
from app.models.superadmin import SuperAdmin
from app.schemas.portal_auth import (
    ForgotPasswordRequest,
    IdentityTokenRequest,
    LoginRequest,
    ManagementTokenRequest,
    MgmtRefreshRequest,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    UnifiedLoginResponse,
)
from app.services import management_auth_service, portal_auth_service
from app.services.audit_service import log_action
from app.utils.dependencies import get_current_superadmin
from app.utils.security import hash_password, verify_password_async

router = APIRouter(prefix="/auth/portal", tags=["portal-auth"])


@router.post("/login", response_model=UnifiedLoginResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> UnifiedLoginResponse:
    """
    Unified portal login — accepts both superadmin and user credentials.

    - superadmin → issues a portal access + refresh token (role-based admin access).
    - user with one portal-capable grant → issues a management JWT.
    - user with multiple grants → returns available_grants list for scope selection.
    - email shared by both a superadmin and a portal-capable user → returns
      available_identities; the client selects one and calls /identity-token.

    Returns HTTP 401 for invalid credentials. The error message is intentionally
    vague — it does not reveal whether the email exists or which table was checked.
    """
    return await management_auth_service.login(db, payload)


@router.post("/identity-token", response_model=UnifiedLoginResponse)
async def identity_token(
    payload: IdentityTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> UnifiedLoginResponse:
    """
    Issue tokens for the chosen identity after cross-identity disambiguation.

    Called by the frontend identity-selector when /login returned
    available_identities (the email matched both a superadmin and a
    portal-capable user). Re-verifies the password for the chosen
    identity_type to prevent identity enumeration.
    """
    return await management_auth_service.issue_identity_token(db, payload)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Exchange a valid portal refresh token for a new portal access + refresh token pair.

    The user's current role is re-read from the DB on each refresh so that
    role changes take effect without requiring a full logout.
    """
    return await portal_auth_service.refresh(db, payload.refresh_token)


@router.post("/management-token", response_model=UnifiedLoginResponse)
async def management_token(
    payload: ManagementTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> UnifiedLoginResponse:
    """
    Issue a management JWT for a specific grant after scope selection.

    Called by the frontend scope-selector when a POS user has multiple
    portal-capable grants. Re-verifies the user's password before issuing
    to prevent grant enumeration by an attacker who intercepted the login response.
    """
    return await management_auth_service.issue_management_token(db, payload)


@router.post("/mgmt-refresh", response_model=UnifiedLoginResponse)
async def mgmt_refresh(
    payload: MgmtRefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> UnifiedLoginResponse:
    """
    Exchange a valid management refresh token for a new management token pair.

    If the user's grants have changed and they now have multiple portal-capable
    grants, returns available_grants instead of tokens so the client can re-select.
    """
    return await management_auth_service.refresh_management_token(db, payload.refresh_token)


class ChangePasswordRequest(BaseModel):
    """Request body for the change-password endpoint."""

    current_password: str
    new_password: str


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> None:
    """
    Change the authenticated portal user's password.

    Requires the current password for verification — prevents an attacker with
    a stolen session token from locking the user out.
    New password must be at least 8 characters.
    """
    if len(payload.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New password must be at least 8 characters.",
        )

    result = await db.execute(select(SuperAdmin).where(SuperAdmin.id == actor.id))
    user = result.scalar_one()

    if not await verify_password_async(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )

    user.password_hash = hash_password(payload.new_password)
    # Revoke tokens issued under the old password (including the one making this
    # request) — the caller's client re-authenticates with the new credential
    user.token_version += 1

    await log_action(
        db=db,
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
        action=AUTH_PASSWORD_CHANGED,
        entity_type="superadmin",
        entity_id=str(user.id),
        after_state={"password_changed": True},
    )

    await db.commit()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> None:
    """
    Log the authenticated portal admin out of all sessions.

    Bumps token_version so every previously issued access and refresh token for
    this admin (across devices/tabs) fails validation on next use. Portal auth
    is stateless, so this "logout everywhere" is the meaningful server-side
    revocation — there is no per-session token to selectively drop.
    """
    result = await db.execute(select(SuperAdmin).where(SuperAdmin.id == actor.id))
    user = result.scalar_one()
    user.token_version += 1  # invalidate all outstanding tokens for this admin

    await log_action(
        db=db,
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
        action=AUTH_LOGOUT,
        entity_type="superadmin",
        entity_id=str(user.id),
        after_state={"logged_out": True},
    )
    await db.commit()


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Request a password reset email.

    Always returns 204 whether or not the email matches a portal user, so the
    endpoint cannot be used to enumerate registered email addresses.
    """
    await portal_auth_service.request_password_reset(db, payload.email)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Complete a password reset using the token emailed by /forgot-password.

    New password must be at least 8 characters. The token is single-use and
    expires after PASSWORD_RESET_EXPIRY_HOURS.
    """
    if len(payload.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New password must be at least 8 characters.",
        )
    await portal_auth_service.reset_password(db, payload.token, payload.new_password)
