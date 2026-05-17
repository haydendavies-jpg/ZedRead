"""Portal authentication routes: login, token refresh, management scope selection, and change password."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.portal_user import PortalUser
from app.schemas.portal_auth import (
    LoginRequest,
    ManagementTokenRequest,
    MgmtRefreshRequest,
    RefreshRequest,
    TokenResponse,
    UnifiedLoginResponse,
)
from app.services import management_auth_service, portal_auth_service
from app.services.audit_service import log_action
from app.constants.audit_actions import AUTH_LOGIN_SUCCESS
from app.utils.dependencies import get_current_portal_user
from app.utils.security import hash_password, verify_password

router = APIRouter(prefix="/auth/portal", tags=["portal-auth"])


@router.post("/login", response_model=UnifiedLoginResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> UnifiedLoginResponse:
    """
    Unified portal login — accepts both portal_user and pos_user credentials.

    - portal_user → issues a portal access + refresh token (role-based admin access).
    - pos_user with can_access_portal profile and one grant → issues a management JWT.
    - pos_user with multiple grants → returns available_grants list for scope selection.

    Returns HTTP 401 for invalid credentials. The error message is intentionally
    vague — it does not reveal whether the email exists or which user table was checked.
    """
    return await management_auth_service.login(db, payload)


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
    actor: PortalUser = Depends(get_current_portal_user),
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

    result = await db.execute(select(PortalUser).where(PortalUser.id == actor.id))
    user = result.scalar_one()

    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )

    user.password_hash = hash_password(payload.new_password)

    await log_action(
        db,
        actor_id=str(user.id),
        actor_type="user",
        actor_email=user.email,
        actor_name=user.name,
        action="auth.password.changed",
        entity_type="portal_user",
        entity_id=str(user.id),
        after_state={"password_changed": True},
    )

    await db.commit()
