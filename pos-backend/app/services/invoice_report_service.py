"""Business logic for invoice reporting (Stage 21) — filtered list, detail view,
and change log.  Read-only: no function here calls log_action().

Split out of invoice_service.py (Stage 10's transactional engine) because
reporting is a distinct responsibility with its own query shapes — the
engine mutates invoices, this module only reads them.

The filtered list reads from vw_invoice_detail (migration 0010), which joins
site_name/brand_name onto the invoice row; per CLAUDE.md rule 6 this is the
documented exception to "always use the ORM" (reporting views are
raw-SQL-only by nature).  Detail/change-log queries use the ORM since they
have no view to read from.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.invoice import Invoice
from app.models.invoice_line_item import InvoiceLineItem
from app.models.invoice_line_modifier import InvoiceLineModifier
from app.models.invoice_tax_breakdown import InvoiceTaxBreakdown
from app.models.payment import Payment

log = structlog.get_logger(__name__)


# ── Inline Pydantic schemas ───────────────────────────────────────────────────

from pydantic import BaseModel


class InvoiceReportRow(BaseModel):
    """One filtered row for the invoice reporting list, sourced from vw_invoice_detail."""

    id: uuid.UUID
    brand_id: uuid.UUID
    site_id: uuid.UUID
    site_name: str
    brand_name: str
    created_by_id: uuid.UUID | None
    invoice_type: str
    status: str
    subtotal_cents: int
    tax_cents: int
    discount_cents: int
    total_cents: int
    refund_of_id: uuid.UUID | None
    is_refunded: bool
    voided_at: datetime | None
    paid_at: datetime | None
    created_at: datetime


class PaymentResponse(BaseModel):
    """Response schema for a payment recorded against an invoice."""

    id: uuid.UUID
    invoice_id: uuid.UUID
    method: str
    amount_cents: int
    reference: str | None
    paid_at: datetime

    model_config = {"from_attributes": True}


class ChangeLogEntry(BaseModel):
    """One audit_logs row rendered for the invoice detail view's change-log panel."""

    id: uuid.UUID
    action: str
    actor_name: str | None
    actor_email: str | None
    actor_type: str
    before_state: dict | None
    after_state: dict | None
    created_at: datetime


class InvoiceDetailResponse(BaseModel):
    """Full invoice detail: header, line items, modifiers, tax breakdown, payments."""

    id: uuid.UUID
    brand_id: uuid.UUID
    site_id: uuid.UUID
    site_name: str
    brand_name: str
    created_by_id: uuid.UUID | None
    invoice_type: str
    status: str
    subtotal_cents: int
    tax_cents: int
    discount_cents: int
    discount_reason: str | None
    total_cents: int
    refund_of_id: uuid.UUID | None
    is_refunded: bool
    voided_at: datetime | None
    paid_at: datetime | None
    created_at: datetime
    line_items: list["InvoiceDetailLineItem"]
    tax_breakdown: list["InvoiceDetailTaxRow"]
    payments: list[PaymentResponse]


class InvoiceDetailLineItem(BaseModel):
    """A line item nested inside the invoice detail response, with its modifiers."""

    id: uuid.UUID
    product_id: uuid.UUID | None
    product_name: str
    unit_price_cents: int
    quantity: int
    subtotal_cents: int
    tax_cents: int
    line_total_cents: int
    display_order: int
    modifiers: list["InvoiceDetailModifier"]


class InvoiceDetailModifier(BaseModel):
    """A modifier nested inside an invoice detail line item."""

    id: uuid.UUID
    modifier_name: str
    price_delta_cents: int


class InvoiceDetailTaxRow(BaseModel):
    """A tax breakdown row nested inside the invoice detail response."""

    id: uuid.UUID
    tax_rate_name: str
    rate_percent: Decimal
    tax_model: str
    taxable_amount_cents: int
    tax_amount_cents: int


InvoiceDetailResponse.model_rebuild()


# ── Helpers ───────────────────────────────────────────────────────────────────

_INVOICE_REPORT_COLUMNS = (
    "id, brand_id, site_id, site_name, brand_name, created_by_id, invoice_type, "
    "status, subtotal_cents, tax_cents, discount_cents, total_cents, refund_of_id, "
    "is_refunded, voided_at, paid_at, created_at"
)


def _build_invoice_filter(
    brand_id: uuid.UUID,
    site_id: uuid.UUID | None,
    start_date: date | None,
    end_date: date | None,
    invoice_status: str | None,
    min_amount_cents: int | None,
    max_amount_cents: int | None,
) -> tuple[str, dict]:
    """
    Build a parameterised WHERE clause for vw_invoice_detail filters.

    Args:
        brand_id: Brand scope (always applied).
        site_id: Optional site filter.
        start_date: Optional lower bound on the invoice's created_at date (inclusive).
        end_date: Optional upper bound on the invoice's created_at date (inclusive).
        invoice_status: Optional invoice status filter (draft/open/paid/voided).
        min_amount_cents: Optional lower bound on total_cents.
        max_amount_cents: Optional upper bound on total_cents.

    Returns:
        tuple[str, dict]: SQL WHERE clause (no "WHERE" keyword) and its bound params.
    """
    clauses = ["brand_id = :brand_id"]
    params: dict = {"brand_id": brand_id}

    if site_id is not None:
        clauses.append("site_id = :site_id")
        params["site_id"] = site_id
    if start_date is not None:
        clauses.append("created_at::date >= :start_date")
        params["start_date"] = start_date
    if end_date is not None:
        clauses.append("created_at::date <= :end_date")
        params["end_date"] = end_date
    if invoice_status is not None:
        clauses.append("status = :invoice_status")
        params["invoice_status"] = invoice_status
    if min_amount_cents is not None:
        clauses.append("total_cents >= :min_amount_cents")
        params["min_amount_cents"] = min_amount_cents
    if max_amount_cents is not None:
        clauses.append("total_cents <= :max_amount_cents")
        params["max_amount_cents"] = max_amount_cents

    return " AND ".join(clauses), params


async def _get_invoice_or_404(db: AsyncSession, brand_id: uuid.UUID, invoice_id: uuid.UUID) -> Invoice:
    """Fetch an invoice scoped to a brand, or raise 404."""
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.brand_id == brand_id)
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice


# ── Public service functions ──────────────────────────────────────────────────


async def list_invoice_reports(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    invoice_status: str | None = None,
    min_amount_cents: int | None = None,
    max_amount_cents: int | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[InvoiceReportRow]:
    """
    Return filtered invoices for a brand from vw_invoice_detail, most recent first.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        site_id: Optional site filter.
        start_date: Optional lower bound on created_at date (inclusive).
        end_date: Optional upper bound on created_at date (inclusive).
        invoice_status: Optional invoice status filter.
        min_amount_cents: Optional lower bound on total_cents.
        max_amount_cents: Optional upper bound on total_cents.
        skip: Pagination offset.
        limit: Maximum rows to return.

    Returns:
        list[InvoiceReportRow]: Matching invoices ordered by created_at descending.
    """
    where, params = _build_invoice_filter(
        brand_id, site_id, start_date, end_date, invoice_status, min_amount_cents, max_amount_cents
    )
    params["skip"] = skip
    params["limit"] = limit
    result = await db.execute(
        text(
            f"SELECT {_INVOICE_REPORT_COLUMNS} FROM vw_invoice_detail "
            f"WHERE {where} ORDER BY created_at DESC OFFSET :skip LIMIT :limit"
        ),
        params,
    )
    rows = result.mappings().all()
    return [InvoiceReportRow(**dict(row)) for row in rows]


async def fetch_invoice_report_rows_for_export(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    invoice_status: str | None = None,
    min_amount_cents: int | None = None,
    max_amount_cents: int | None = None,
    max_rows: int = 20000,
) -> list[dict]:
    """
    Return raw filtered invoice rows (as dicts) for XLSX export — unpaginated,
    capped at max_rows as a safety limit against unbounded exports.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        site_id: Optional site filter.
        start_date: Optional lower bound on created_at date (inclusive).
        end_date: Optional upper bound on created_at date (inclusive).
        invoice_status: Optional invoice status filter.
        min_amount_cents: Optional lower bound on total_cents.
        max_amount_cents: Optional upper bound on total_cents.
        max_rows: Hard cap on rows returned.

    Returns:
        list[dict]: Matching invoice rows ordered by created_at descending.
    """
    where, params = _build_invoice_filter(
        brand_id, site_id, start_date, end_date, invoice_status, min_amount_cents, max_amount_cents
    )
    params["max_rows"] = max_rows
    result = await db.execute(
        text(
            f"SELECT {_INVOICE_REPORT_COLUMNS} FROM vw_invoice_detail "
            f"WHERE {where} ORDER BY created_at DESC LIMIT :max_rows"
        ),
        params,
    )
    return [dict(row) for row in result.mappings().all()]


async def get_invoice_site_id(db: AsyncSession, brand_id: uuid.UUID, invoice_id: uuid.UUID) -> uuid.UUID:
    """
    Return the site_id for an invoice, scoped to a brand.

    A lightweight lookup routes use to enforce site-level access before
    fetching the full detail or change-log payload.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        invoice_id: Invoice to check.

    Returns:
        uuid.UUID: The invoice's site_id.

    Raises:
        HTTPException: 404 if the invoice does not exist within the brand.
    """
    invoice = await _get_invoice_or_404(db, brand_id, invoice_id)
    return invoice.site_id


async def get_invoice_detail(
    db: AsyncSession, brand_id: uuid.UUID, invoice_id: uuid.UUID
) -> InvoiceDetailResponse:
    """
    Return the full detail of one invoice: header, line items with their
    modifiers, tax breakdown, and payments.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        invoice_id: Invoice to fetch.

    Returns:
        InvoiceDetailResponse: The assembled invoice detail.

    Raises:
        HTTPException: 404 if the invoice does not exist within the brand.
    """
    invoice = await _get_invoice_or_404(db, brand_id, invoice_id)

    site_brand_result = await db.execute(
        text("SELECT site_name, brand_name FROM vw_invoice_detail WHERE id = :invoice_id"),
        {"invoice_id": invoice_id},
    )
    site_brand = site_brand_result.mappings().one()

    items_result = await db.execute(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == invoice_id)
        .order_by(InvoiceLineItem.display_order)
    )
    items = items_result.scalars().all()

    line_items: list[InvoiceDetailLineItem] = []
    for item in items:
        mods_result = await db.execute(
            select(InvoiceLineModifier).where(InvoiceLineModifier.line_item_id == item.id)
        )
        modifiers = [
            InvoiceDetailModifier(id=m.id, modifier_name=m.modifier_name, price_delta_cents=m.price_delta_cents)
            for m in mods_result.scalars().all()
        ]
        line_items.append(
            InvoiceDetailLineItem(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                unit_price_cents=item.unit_price_cents,
                quantity=item.quantity,
                subtotal_cents=item.subtotal_cents,
                tax_cents=item.tax_cents,
                line_total_cents=item.line_total_cents,
                display_order=item.display_order,
                modifiers=modifiers,
            )
        )

    tax_result = await db.execute(
        select(InvoiceTaxBreakdown).where(InvoiceTaxBreakdown.invoice_id == invoice_id)
    )
    tax_breakdown = [
        InvoiceDetailTaxRow(
            id=t.id,
            tax_rate_name=t.tax_rate_name,
            rate_percent=t.rate_percent,
            tax_model=t.tax_model,
            taxable_amount_cents=t.taxable_amount_cents,
            tax_amount_cents=t.tax_amount_cents,
        )
        for t in tax_result.scalars().all()
    ]

    payments_result = await db.execute(
        select(Payment).where(Payment.invoice_id == invoice_id).order_by(Payment.paid_at)
    )
    payments = [PaymentResponse.model_validate(p) for p in payments_result.scalars().all()]

    return InvoiceDetailResponse(
        id=invoice.id,
        brand_id=invoice.brand_id,
        site_id=invoice.site_id,
        site_name=site_brand["site_name"],
        brand_name=site_brand["brand_name"],
        created_by_id=invoice.created_by_id,
        invoice_type=invoice.invoice_type,
        status=invoice.status,
        subtotal_cents=invoice.subtotal_cents,
        tax_cents=invoice.tax_cents,
        discount_cents=invoice.discount_cents,
        discount_reason=invoice.discount_reason,
        total_cents=invoice.total_cents,
        refund_of_id=invoice.refund_of_id,
        is_refunded=invoice.is_refunded,
        voided_at=invoice.voided_at,
        paid_at=invoice.paid_at,
        created_at=invoice.created_at,
        line_items=line_items,
        tax_breakdown=tax_breakdown,
        payments=payments,
    )


async def get_invoice_change_log(
    db: AsyncSession, brand_id: uuid.UUID, invoice_id: uuid.UUID
) -> list[ChangeLogEntry]:
    """
    Return the audit trail for one invoice: every audit_logs row recorded
    directly against it (create, discount, pay, void, refund), oldest first.

    Args:
        db: Active database session.
        brand_id: Brand scope — validates the invoice belongs to this brand
            before returning any log rows.
        invoice_id: Invoice to fetch the change log for.

    Returns:
        list[ChangeLogEntry]: Audit rows ordered by created_at ascending.

    Raises:
        HTTPException: 404 if the invoice does not exist within the brand.
    """
    await _get_invoice_or_404(db, brand_id, invoice_id)  # validates brand scope

    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.entity_type == "invoice", AuditLog.entity_id == str(invoice_id))
        .order_by(AuditLog.created_at.asc())
    )
    rows = result.scalars().all()
    return [
        ChangeLogEntry(
            id=row.id,
            action=row.action,
            actor_name=row.actor_name,
            actor_email=row.actor_email,
            actor_type=row.actor_type,
            before_state=row.before_state,
            after_state=row.after_state,
            created_at=row.created_at,
        )
        for row in rows
    ]
