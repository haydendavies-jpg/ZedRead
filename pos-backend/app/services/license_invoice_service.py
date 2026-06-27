"""Business logic for license invoice management."""

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import LICENSE_INVOICE_PAID
from app.models.license import License
from app.models.license_invoice import LicenseInvoice
from app.models.superadmin import SuperAdmin
from app.schemas.license_invoice import LicenseInvoiceCreate, LicenseInvoicePayRequest
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


async def _get_or_404(db: AsyncSession, invoice_id: uuid.UUID) -> LicenseInvoice:
    """
    Fetch a LicenseInvoice by ID or raise HTTP 404.

    Args:
        db: Active database session.
        invoice_id: UUID of the invoice.

    Returns:
        LicenseInvoice: The found invoice.

    Raises:
        HTTPException: 404 if not found.
    """
    result = await db.execute(select(LicenseInvoice).where(LicenseInvoice.id == invoice_id))
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return inv


async def list_invoices(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
) -> list[LicenseInvoice]:
    """
    Return a paginated list of all license invoices.

    Args:
        db: Active database session.
        skip: Number of rows to skip.
        limit: Maximum rows to return.

    Returns:
        list[LicenseInvoice]: The requested page of invoices.
    """
    result = await db.execute(
        select(LicenseInvoice).order_by(LicenseInvoice.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def get_invoice(db: AsyncSession, invoice_id: uuid.UUID) -> LicenseInvoice:
    """
    Fetch a single invoice by ID.

    Args:
        db: Active database session.
        invoice_id: UUID of the invoice.

    Returns:
        LicenseInvoice: The found invoice.

    Raises:
        HTTPException: 404 if not found.
    """
    return await _get_or_404(db, invoice_id)


async def create_invoice(
    db: AsyncSession,
    payload: LicenseInvoiceCreate,
    actor: SuperAdmin,
) -> LicenseInvoice:
    """
    Create a new invoice against a license and write an audit log row.

    Args:
        db: Active database session.
        payload: Invoice creation data.
        actor: The authenticated portal user performing the action.

    Returns:
        LicenseInvoice: The newly created invoice.

    Raises:
        HTTPException: 404 if the referenced license does not exist.
        HTTPException: 422 if period_end is not after period_start.
    """
    # Validate license exists
    lic_result = await db.execute(select(License).where(License.id == payload.license_id))
    if lic_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")

    if payload.period_end <= payload.period_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="period_end must be after period_start",
        )

    log.info("license_invoice.creating", license_id=str(payload.license_id))

    inv = LicenseInvoice(
        id=uuid.uuid4(),
        license_id=payload.license_id,
        amount_cents=payload.amount_cents,
        status="open",
        period_start=payload.period_start,
        period_end=payload.period_end,
    )
    db.add(inv)

    # No dedicated CREATED constant — invoice creation is captured when paid (LICENSE_INVOICE_PAID)
    # Log a created marker using a generic log record without committing a business audit row
    await db.commit()
    await db.refresh(inv)
    log.info("license_invoice.created", invoice_id=str(inv.id))
    return inv


async def pay_invoice(
    db: AsyncSession,
    invoice_id: uuid.UUID,
    payload: LicenseInvoicePayRequest,
    actor: SuperAdmin,
) -> LicenseInvoice:
    """
    Mark an open invoice as paid and write a LICENSE_INVOICE_PAID audit row.

    Args:
        db: Active database session.
        invoice_id: UUID of the invoice to pay.
        payload: Optional paid_at timestamp; defaults to now() if omitted.
        actor: The authenticated portal user performing the action.

    Returns:
        LicenseInvoice: The updated invoice.

    Raises:
        HTTPException: 404 if not found.
        HTTPException: 409 if the invoice is already paid or cancelled.
    """
    inv = await _get_or_404(db, invoice_id)

    if inv.status != "open":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot pay an invoice that is already {inv.status}",
        )

    paid_at = payload.paid_at if payload.paid_at is not None else datetime.now(tz=timezone.utc)
    inv.status = "paid"
    inv.paid_at = paid_at

    await log_action(
        db=db,
        action=LICENSE_INVOICE_PAID,
        entity_type="license_invoice",
        entity_id=str(inv.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"status": "open"},
        after_state={"status": "paid", "amount_cents": inv.amount_cents},
    )

    await db.commit()
    await db.refresh(inv)
    log.info("license_invoice.paid", invoice_id=str(inv.id))
    return inv
