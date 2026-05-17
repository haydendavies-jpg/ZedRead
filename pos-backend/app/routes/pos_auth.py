"""POS terminal authentication routes: login, PIN set, and PIN verify."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.pos_auth import (
    PINSetRequest,
    PINVerifyRequest,
    PINVerifyResponse,
    POSLoginRequest,
    POSLoginResponse,
)
from app.services import pos_auth_service
from app.utils.dependencies import POSAccess, resolve_access

router = APIRouter(prefix="/auth/pos", tags=["pos-auth"])


@router.post("/login", response_model=POSLoginResponse, status_code=status.HTTP_200_OK)
async def pos_login(
    payload: POSLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> POSLoginResponse:
    """
    Authenticate a POS user with email + password for a specific site.

    Returns a POS access JWT and contextual information the terminal needs
    to display (user name, site name, access profile).

    Args:
        payload: Login credentials and target site.
        db: Active database session.

    Returns:
        POSLoginResponse: Token and terminal context.
    """
    return await pos_auth_service.login(db, payload)


@router.post("/pin/set", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def set_pin(
    payload: PINSetRequest,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Set or replace the PIN for the currently authenticated POS user.

    Requires a valid POS access token. Clears the is_pin_reset_required flag
    so the terminal stops prompting for a new PIN after first login.

    Args:
        payload: The new PIN (4–6 digits).
        access: Resolved POS access (user, site, profile) from JWT.
        db: Active database session.
    """
    await pos_auth_service.set_pin(db, access.user, payload)


@router.post("/pin/verify", response_model=PINVerifyResponse, status_code=status.HTTP_200_OK)
async def verify_pin(
    payload: PINVerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> PINVerifyResponse:
    """
    Verify a POS user's PIN and return a fresh access token.

    Used for terminal switch-user: a different staff member can take over
    without the current user logging out. No existing session is required —
    this endpoint is intentionally unauthenticated so any staff member can
    appear on an idle terminal.

    Args:
        payload: Email, PIN, and site_id of the incoming user.
        db: Active database session.

    Returns:
        PINVerifyResponse: Fresh access token and user context.
    """
    return await pos_auth_service.verify_pin(db, payload)
