"""Business logic for register (till) session reporting — filtered list only.

Read-only: no function here calls log_action(). Split out of
register_session_service.py (which owns the open/close/lookup transactional
flows the POS terminal calls) because reporting is a distinct responsibility
with its own query shape, matching the invoice_service.py /
invoice_report_service.py split from Stage 21.

register_sessions has no reporting view (unlike vw_invoice_detail) — its
row count per brand is small (one per device per shift), so a plain ORM
join to pos_devices/sites for device_name/site_name is used instead of
introducing a migration for a view.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.pos_device import PosDevice
from app.models.register_session import RegisterSession
from app.models.site import Site


class RegisterSessionReportRow(BaseModel):
    """One row of the register-session reporting list, joined to its device/site names."""

    id: uuid.UUID
    device_id: uuid.UUID
    device_name: str
    site_id: uuid.UUID
    site_name: str
    status: str
    opened_at: datetime
    opening_cash_cents: int
    opened_by_name: str
    closed_at: datetime | None
    closing_cash_cents: int | None
    expected_cash_cents: int | None
    cash_takings_cents: int | None
    variance_cents: int | None
    closed_by_name: str | None

    model_config = {"from_attributes": True}


async def list_register_session_reports(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
    session_status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[RegisterSessionReportRow]:
    """
    Return filtered register sessions for a brand, most recently opened first.

    Args:
        db: Active database session.
        brand_id: Brand scope (via the session's site).
        site_id: Optional site filter.
        device_id: Optional device (terminal) filter.
        session_status: Optional status filter — open/closed.
        start_date: Optional lower bound on opened_at date (inclusive).
        end_date: Optional upper bound on opened_at date (inclusive).
        skip: Pagination offset.
        limit: Maximum rows to return.

    Returns:
        list[RegisterSessionReportRow]: Matching sessions ordered by opened_at descending.
    """
    query = (
        select(
            RegisterSession,
            PosDevice.device_name,
            Site.name.label("site_name"),
        )
        .join(PosDevice, PosDevice.id == RegisterSession.device_id)
        .join(Site, Site.id == RegisterSession.site_id)
        .where(Site.brand_id == brand_id)
    )
    if site_id is not None:
        query = query.where(RegisterSession.site_id == site_id)
    if device_id is not None:
        query = query.where(RegisterSession.device_id == device_id)
    if session_status is not None:
        query = query.where(RegisterSession.status == session_status)
    if start_date is not None:
        query = query.where(cast(RegisterSession.opened_at, Date) >= start_date)
    if end_date is not None:
        query = query.where(cast(RegisterSession.opened_at, Date) <= end_date)

    query = query.order_by(RegisterSession.opened_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    rows: list[RegisterSessionReportRow] = []
    for session, device_name, site_name in result.all():
        cash_takings_cents = (
            session.expected_cash_cents - session.opening_cash_cents
            if session.expected_cash_cents is not None
            else None
        )
        rows.append(
            RegisterSessionReportRow(
                id=session.id,
                device_id=session.device_id,
                device_name=device_name,
                site_id=session.site_id,
                site_name=site_name,
                status=session.status,
                opened_at=session.opened_at,
                opening_cash_cents=session.opening_cash_cents,
                opened_by_name=session.opened_by_name,
                closed_at=session.closed_at,
                closing_cash_cents=session.closing_cash_cents,
                expected_cash_cents=session.expected_cash_cents,
                cash_takings_cents=cash_takings_cents,
                variance_cents=session.variance_cents,
                closed_by_name=session.closed_by_name,
            )
        )
    return rows


async def get_payment_breakdown_for_session(db: AsyncSession, session_id: uuid.UUID) -> dict[str, int]:
    """
    Sum payment amounts by method for every invoice raised under one register session.

    Backs the register_summary print template's PAYMENT_METHOD_BREAKDOWN
    field — Payment has no direct register_session_id column, so this joins
    through Invoice.register_session_id instead.

    Args:
        db: Active database session.
        session_id: The register session to summarise.

    Returns:
        dict[str, int]: {payment_method: total_amount_cents}, only methods with at least one payment.
    """
    result = await db.execute(
        select(Payment.method, func.sum(Payment.amount_cents))
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .where(Invoice.register_session_id == session_id)
        .group_by(Payment.method)
    )
    return {method: int(total) for method, total in result.all()}
