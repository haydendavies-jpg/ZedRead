"""Business logic for POS register (till) sessions — open, close, and lookup."""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import REGISTER_SESSION_CLOSED, REGISTER_SESSION_OPENED
from app.constants.statuses import ActorType, PaymentMethod
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.pos_device import PosDevice
from app.models.register_session import RegisterSession
from app.models.user import User
from app.schemas.register_session import RegisterSessionCloseRequest, RegisterSessionOpenRequest
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


async def _get_or_404(db: AsyncSession, session_id: uuid.UUID) -> RegisterSession:
    """
    Fetch a RegisterSession by ID or raise HTTP 404.

    Args:
        db: Active database session.
        session_id: UUID of the register session.

    Returns:
        RegisterSession: The found session.

    Raises:
        HTTPException: 404 if not found.
    """
    result = await db.execute(select(RegisterSession).where(RegisterSession.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Register session not found")
    return session


async def get_open_session_for_device(
    db: AsyncSession, device_id: uuid.UUID
) -> RegisterSession | None:
    """
    Fetch the currently open register session for a device, if any.

    Args:
        db: Active database session.
        device_id: UUID of the terminal.

    Returns:
        RegisterSession | None: The open session, or None if the till hasn't
            been opened for this device yet.
    """
    result = await db.execute(
        select(RegisterSession).where(
            RegisterSession.device_id == device_id,
            RegisterSession.status == "open",
        )
    )
    return result.scalar_one_or_none()


async def get_open_session_or_400(db: AsyncSession, device: PosDevice | None) -> RegisterSession:
    """
    Resolve the open register session a new invoice must be attributed to.

    Used by invoice_service.create_invoice() to enforce that a sale cannot be
    rung up before start-of-day cash has been entered for the device.

    Args:
        db: Active database session.
        device: The calling terminal's PosDevice, or None if the POS token
            carries no device context (e.g. a PIN-verify switch that didn't
            supply device_token).

    Returns:
        RegisterSession: The device's currently open session.

    Raises:
        HTTPException: 400 if there is no device context or no open session.
    """
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This session has no associated device — please log in again",
        )
    session = await get_open_session_for_device(db, device.id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No open register session for this device — enter start-of-day cash before selling",
        )
    return session


async def open_register_session(
    db: AsyncSession,
    payload: RegisterSessionOpenRequest,
    device: PosDevice,
    actor: User,
) -> RegisterSession:
    """
    Open a new register session for a device.

    Rejects with 409 if a session is already open for this device — a
    partial unique index also enforces this at the DB level as a
    defence-in-depth backstop against a concurrent double-open.

    Args:
        db: Active database session.
        payload: Opening cash and the device-local opened_at timestamp.
        device: The terminal being opened (already resolved from device_token).
        actor: The authenticated POS user opening the till.

    Returns:
        RegisterSession: The newly opened session.

    Raises:
        HTTPException: 409 if a session is already open for this device.
    """
    existing = await get_open_session_for_device(db, device.id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A register session is already open for this device",
        )

    session = RegisterSession(
        id=uuid.uuid4(),
        device_id=device.id,
        site_id=device.site_id,
        status="open",
        opened_at=payload.opened_at,
        opening_cash_cents=payload.opening_cash_cents,
        opened_by_user_id=actor.id,
        opened_by_name=actor.name,
    )
    db.add(session)

    await log_action(
        db=db,
        action=REGISTER_SESSION_OPENED,
        entity_type="register_session",
        entity_id=str(session.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "device_id": str(device.id),
            "site_id": str(device.site_id),
            "opening_cash_cents": payload.opening_cash_cents,
        },
    )
    await db.commit()
    await db.refresh(session)
    log.info("register_session.opened", session_id=str(session.id), device_id=str(device.id))
    return session


async def close_register_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    payload: RegisterSessionCloseRequest,
    actor: User,
) -> RegisterSession:
    """
    Close an open register session, computing expected cash and variance.

    expected_cash_cents = opening_cash_cents + sum of cash payments recorded
    against invoices raised under this session. variance_cents is the
    difference between what was actually counted and that expectation —
    positive means over, negative means short.

    Args:
        db: Active database session.
        session_id: The session to close.
        payload: Closing cash and the device-local closed_at timestamp.
        actor: The authenticated POS user closing the till.

    Returns:
        RegisterSession: The closed session.

    Raises:
        HTTPException: 404 if the session doesn't exist; 400 if it's already closed.
    """
    session = await _get_or_404(db, session_id)
    if session.status != "open":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Register session is already closed",
        )

    cash_result = await db.execute(
        select(func.coalesce(func.sum(Payment.amount_cents), 0))
        .select_from(Payment)
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .where(
            Invoice.register_session_id == session.id,
            Payment.method == PaymentMethod.CASH.value,
        )
    )
    # SUM() over a BigInteger column comes back as a Decimal via
    # asyncpg/Postgres NUMERIC — cast back to int so downstream arithmetic
    # and the after_state audit dict stay JSON-serializable
    cash_takings_cents = int(cash_result.scalar_one())

    expected_cents = session.opening_cash_cents + cash_takings_cents
    variance_cents = payload.closing_cash_cents - expected_cents

    session.status = "closed"
    session.closed_at = payload.closed_at
    session.closing_cash_cents = payload.closing_cash_cents
    session.expected_cash_cents = expected_cents
    session.variance_cents = variance_cents
    session.closed_by_user_id = actor.id
    session.closed_by_name = actor.name

    await log_action(
        db=db,
        action=REGISTER_SESSION_CLOSED,
        entity_type="register_session",
        entity_id=str(session.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"status": "open"},
        after_state={
            "closing_cash_cents": payload.closing_cash_cents,
            "expected_cash_cents": expected_cents,
            "variance_cents": variance_cents,
        },
    )
    await db.commit()
    await db.refresh(session)
    log.info(
        "register_session.closed",
        session_id=str(session.id),
        variance_cents=variance_cents,
    )
    return session


async def get_current_session_for_device(
    db: AsyncSession, device: PosDevice
) -> RegisterSession | None:
    """
    Fetch the open register session for a device, for the POS to display on load.

    Args:
        db: Active database session.
        device: The terminal to check.

    Returns:
        RegisterSession | None: The open session, or None if the till is closed.
    """
    return await get_open_session_for_device(db, device.id)
