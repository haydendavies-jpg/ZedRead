"""POS user invite routes: create invite and accept invite."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.user_invite import InviteAcceptRequest, InviteCreateRequest, InviteResponse
from app.services import user_invite_service
from app.utils.dependencies import POSAccess, resolve_access

router = APIRouter(prefix="/invites", tags=["invites"])


@router.post("", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
async def create_invite(
    payload: InviteCreateRequest,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> InviteResponse:
    """
    Send a POS user invitation email for the authenticated user's brand.

    Requires a valid POS access token. The invite is scoped to the brand
    associated with the authenticated user — cross-brand invites are rejected
    with 404.

    Args:
        payload: Invite data (email, site_id, access_profile_id).
        access: Resolved POS access (user, site, profile) from JWT.
        db: Active database session.

    Returns:
        InviteResponse: The created invite row (token is NOT returned for security).
    """
    return await user_invite_service.create_invite(
        db=db,
        brand_id=access.user.brand_id,
        payload=payload,
        actor=access.user,
    )


@router.post("/accept", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def accept_invite(
    payload: InviteAcceptRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Accept a pending invite and create the POS user account.

    This endpoint is intentionally unauthenticated — the invite token itself
    serves as the authentication credential. The token is single-use and
    expires after the configured INVITE_EXPIRY_HOURS.

    Args:
        payload: Accept data (token, name, password).
        db: Active database session.
    """
    await user_invite_service.accept_invite(db, payload)
