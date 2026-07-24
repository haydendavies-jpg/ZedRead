"""Routes for POS register (till) sessions — open, close, and current-state lookup."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.register_session import (
    RegisterSessionCloseRequest,
    RegisterSessionOpenRequest,
    RegisterSessionOut,
)
from app.services import register_session_report_service, register_session_service
from app.utils.dependencies import POSAccess, resolve_access

router = APIRouter(prefix="/register-sessions", tags=["register-sessions"])


@router.get("/current", response_model=RegisterSessionOut | None, status_code=status.HTTP_200_OK)
async def get_current_session(
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> RegisterSessionOut | None:
    """
    Fetch the open register session for this terminal, if any.

    The POS app calls this on launch to decide whether to show the
    start-of-day cash-in gate or go straight to the Register screen.

    Args:
        access: Resolved POS access (carries the terminal's device).
        db: Active database session.

    Returns:
        RegisterSessionOut | None: The open session, or None if the till is closed.
    """
    if access.device is None:
        return None
    session = await register_session_service.get_current_session_for_device(db, access.device)
    return RegisterSessionOut.model_validate(session) if session else None


@router.post("/open", response_model=RegisterSessionOut, status_code=status.HTTP_201_CREATED)
async def open_session(
    payload: RegisterSessionOpenRequest,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> RegisterSessionOut:
    """
    Open a new register session (start-of-day cash-in) for this terminal.

    Args:
        payload: Opening cash and the device-local opened_at timestamp.
        access: Resolved POS access (carries the terminal's device and actor).
        db: Active database session.

    Returns:
        RegisterSessionOut: The newly opened session.

    Raises:
        HTTPException: 400 if the token has no device context; 409 if a
            session is already open for this device.
    """
    if access.device is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This session has no associated device — please log in again",
        )
    session = await register_session_service.open_register_session(
        db, payload, access.device, access.user
    )
    return RegisterSessionOut.model_validate(session)


@router.post(
    "/{session_id}/close", response_model=RegisterSessionOut, status_code=status.HTTP_200_OK
)
async def close_session(
    session_id: uuid.UUID,
    payload: RegisterSessionCloseRequest,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> RegisterSessionOut:
    """
    Close a register session (end-of-day cash-up).

    Args:
        session_id: The session to close.
        payload: Closing cash and the device-local closed_at timestamp.
        access: Resolved POS access (the closing actor).
        db: Active database session.

    Returns:
        RegisterSessionOut: The closed session, including computed variance and
            the payment-method breakdown for the register_summary print template.

    Raises:
        HTTPException: 404 if the session doesn't exist; 400 if already closed.
    """
    session = await register_session_service.close_register_session(
        db, session_id, payload, access.user
    )
    breakdown = await register_session_report_service.get_payment_breakdown_for_session(db, session.id)
    return RegisterSessionOut.model_validate(session).model_copy(update={"payment_breakdown_cents": breakdown})
