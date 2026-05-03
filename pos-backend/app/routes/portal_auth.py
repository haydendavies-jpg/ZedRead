"""Portal authentication routes: login and token refresh.

These routes do not require an existing authenticated session — they are the
entry points for creating one.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.portal_auth import LoginRequest, RefreshRequest, TokenResponse
from app.services import portal_auth_service

router = APIRouter(prefix="/auth/portal", tags=["portal-auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate a portal user and return an access + refresh token pair.

    Returns HTTP 401 for invalid credentials. The error message is intentionally
    vague — it does not reveal whether the email address exists in the system.
    """
    return await portal_auth_service.login(db, payload)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Exchange a valid refresh token for a new access + refresh token pair.

    The user's current role is re-read from the DB on each refresh so that
    role changes take effect without requiring a full logout.
    """
    return await portal_auth_service.refresh(db, payload.refresh_token)
