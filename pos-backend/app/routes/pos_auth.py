"""POS terminal authentication routes: login, PIN set, and PIN verify."""

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.pos_auth import (
    PINSetRequest,
    PINVerifyRequest,
    PINVerifyResponse,
    POSLoginRequest,
    POSLoginResponse,
    POSLogoutResponse,
)
from app.services import pos_auth_service
from app.utils.dependencies import POSAccess, resolve_access
from app.utils.security import decode_token

router = APIRouter(prefix="/auth/pos", tags=["pos-auth"])

# Extracts the Bearer token so logout can read the session jti from the token
_bearer = HTTPBearer()


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


@router.post("/logout", response_model=POSLogoutResponse, status_code=status.HTTP_200_OK)
async def pos_logout(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> POSLogoutResponse:
    """
    End the current POS session, revoking the presented access token.

    Requires a valid POS access token (resolve_access also confirms the session
    is still active). The token's jti is read to end exactly this session, so a
    switched-out user's other sessions are unaffected.

    Args:
        credentials: Bearer token — the jti identifies which session to end.
        access: Resolved POS access (authenticates the caller).
        db: Active database session.

    Returns:
        POSLogoutResponse: Confirmation the session was ended.
    """
    # resolve_access already validated the token; decode again only to read jti
    payload = decode_token(credentials.credentials, expected_type="pos_access")
    await pos_auth_service.logout(db, access.user, payload.get("jti", ""))
    return POSLogoutResponse()


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
