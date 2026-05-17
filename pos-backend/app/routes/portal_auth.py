"""Portal authentication routes: login, token refresh, and management scope selection.

These routes do not require an existing authenticated session — they are the
entry points for creating one.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.portal_auth import (
    LoginRequest,
    ManagementTokenRequest,
    MgmtRefreshRequest,
    RefreshRequest,
    TokenResponse,
    UnifiedLoginResponse,
)
from app.services import management_auth_service, portal_auth_service

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
