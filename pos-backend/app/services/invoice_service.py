"""Business logic for the invoice engine.

Workflow:
  1. create_invoice()      — create a DRAFT invoice for the site
  2. add_line_item()       — add a product; snapshots all mutable fields
  3. add_line_modifier()   — attach a modifier to a line item
  4. apply_discount()      — record a flat discount_cents + reason
  5. pay_invoice()         — record payment; marks PAID when fully covered
  6. void_invoice()        — mark VOIDED (cannot void a PAID invoice)
  7. create_refund()       — create a negative/refund PAID invoice

Snapshot rule: InvoiceLineItem stores product_name, unit_price_cents,
tax_category_name, tax_rate_percent, tax_model as COPIED values at creation
time.  These fields must never be updated after the line item is created.
"""

import uuid
from collections import defaultdict
from datetime import datetime, timezone

import structlog
from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    INVOICE_CREATED,
    INVOICE_DISCOUNT_APPLIED,
    INVOICE_LINE_ITEM_ADDED,
    INVOICE_LINE_ITEM_MODIFIER_ADDED,
    INVOICE_LINE_ITEM_QUANTITY_UPDATED,
    INVOICE_LINE_ITEM_REMOVED,
    INVOICE_PAID,
    INVOICE_PAYMENT_RECORDED,
    INVOICE_REFUNDED,
    INVOICE_VOIDED,
)
from app.constants.statuses import ActorType, InvoiceStatus, InvoiceType
from app.models.invoice import Invoice
from app.models.invoice_line_item import InvoiceLineItem
from app.models.invoice_line_modifier import InvoiceLineModifier
from app.models.invoice_tax_breakdown import InvoiceTaxBreakdown
from app.models.modifier_option import ModifierOption
from app.models.payment import Payment
from app.models.user import User
from app.models.product import Product
from app.services.audit_service import log_action
from app.utils.checksum import verify_checksum

log = structlog.get_logger(__name__)


# ── Inline Pydantic schemas ───────────────────────────────────────────────────

from decimal import Decimal

from pydantic import BaseModel, Field


class InvoiceResponse(BaseModel):
    """Response schema for an invoice."""

    id: uuid.UUID
    ref: str
    brand_id: uuid.UUID
    site_id: uuid.UUID
    created_by_id: uuid.UUID | None
    register_session_id: uuid.UUID | None
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
    client_ref: str | None = None
    checksum: str | None = None
    # Distinct payment methods recorded against this invoice (e.g. ["cash",
    # "card"] for a split payment) — powers the Register's invoice history
    # list, which shows payment method(s) as a per-row column. Not populated
    # by from_attributes (Invoice has no such ORM attribute); list_invoices()'s
    # route caller fills this in via get_payment_methods_by_invoice() after
    # the fact, same pattern as invoice_report_service.InvoiceReportRow's own
    # payment_methods field. Defaults to empty for every other InvoiceResponse
    # call site (create/pay/discount/void/refund), which don't need it.
    payment_methods: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class LineItemResponse(BaseModel):
    """Response schema for an invoice line item."""

    id: uuid.UUID
    invoice_id: uuid.UUID
    product_id: uuid.UUID | None
    product_name: str
    unit_price_cents: int
    tax_category_name: str | None
    tax_rate_percent: Decimal
    tax_model: str
    quantity: int
    subtotal_cents: int
    tax_cents: int
    line_total_cents: int
    display_order: int

    model_config = {"from_attributes": True}


class LineModifierResponse(BaseModel):
    """Response schema for an invoice line modifier."""

    id: uuid.UUID
    line_item_id: uuid.UUID
    modifier_option_id: uuid.UUID | None
    modifier_name: str
    price_delta_cents: int

    model_config = {"from_attributes": True}


class LineItemDetailResponse(LineItemResponse):
    """
    A line item plus its currently attached modifiers.

    Used to refresh a line's display state after attaching one or more
    modifiers via add_line_modifier() — that route returns only the created
    LineModifierResponse row, not the parent line, so a caller building a
    full order-line display (item + its modifier sub-lines) needs this to
    fetch the accumulated set.
    """

    modifiers: list[LineModifierResponse]


class AddLineItemRequest(BaseModel):
    """Payload for adding a product line item to an invoice."""

    product_id: uuid.UUID
    quantity: int = Field(1, ge=1)
    display_order: int = Field(0, ge=0)
    notes: str | None = None


class AddModifierRequest(BaseModel):
    """Payload for adding a modifier to a line item."""

    modifier_option_id: uuid.UUID


class UpdateLineItemQuantityRequest(BaseModel):
    """Payload for changing a line item's quantity."""

    quantity: int = Field(..., ge=1)


class ApplyDiscountRequest(BaseModel):
    """Payload for applying a discount to an invoice."""

    discount_cents: int = Field(..., ge=0)
    reason: str | None = None


class InvoiceCreateRequest(BaseModel):
    """
    Payload for POST /invoices.

    All fields optional — site/brand/register-session resolve server-side
    from the caller's POS token, this only carries the offline-sync
    idempotency key.
    """

    client_ref: str | None = Field(
        None, description="Client-generated idempotency key — a retried create with the same value is deduped"
    )


class PayInvoiceRequest(BaseModel):
    """Payload for recording a payment."""

    method: str = Field(..., pattern="^(cash|card|voucher)$")
    amount_cents: int = Field(..., ge=1)
    reference: str | None = None
    client_ref: str | None = Field(
        None, description="Client-generated idempotency key — a retried pay call with the same value is deduped"
    )
    checksum: str | None = Field(
        None,
        description="SHA-256 over the invoice's canonical line items/totals/payments after this payment — verified if supplied",
    )


class RefundRequest(BaseModel):
    """
    Payload for creating a refund invoice.

    line_item_ids, when supplied and non-empty, requests a PARTIAL refund —
    only those line items (plus their modifiers) are refunded, by whole
    item (no partial-quantity-within-a-line support — see create_refund's
    doc). Omitted or empty means a full refund of the entire invoice, same
    as before this field existed.
    """

    reason: str | None = None
    line_item_ids: list[uuid.UUID] | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_invoice_or_404(
    db: AsyncSession, brand_id: uuid.UUID, invoice_id: uuid.UUID
) -> Invoice:
    """Fetch an invoice scoped to a brand, or raise 404."""
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.brand_id == brand_id)
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return inv


async def _recompute_invoice_totals(db: AsyncSession, invoice: Invoice) -> None:
    """
    Recompute invoice subtotal_cents, tax_cents, and total_cents from line items.

    Called after adding/removing line items or applying a discount.
    Uses a database query to sum all line item values so in-session
    additions are included after flush.
    """
    items_result = await db.execute(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice.id)
    )
    items = items_result.scalars().all()

    # Also add modifier price deltas to the subtotal
    modifier_total = 0
    for item in items:
        mods_result = await db.execute(
            select(InvoiceLineModifier).where(InvoiceLineModifier.line_item_id == item.id)
        )
        mods = mods_result.scalars().all()
        modifier_total += sum(m.price_delta_cents for m in mods)

    subtotal = sum(i.subtotal_cents for i in items) + modifier_total
    tax = sum(i.tax_cents for i in items)
    # For exclusive tax: total = subtotal + tax - discount
    # For inclusive: tax is embedded in subtotal so total = subtotal - discount
    # line_total already accounts for which type each line is
    line_total_sum = sum(i.line_total_cents for i in items) + modifier_total
    total = line_total_sum - invoice.discount_cents

    invoice.subtotal_cents = subtotal
    invoice.tax_cents = tax
    invoice.total_cents = max(0, total)  # never negative (discount cannot exceed total)


async def _build_invoice_checksum_payload(db: AsyncSession, invoice: Invoice) -> dict:
    """
    Build the canonical dict pay_invoice() checksums an invoice's current state against.

    Covers line items and payments (per CLAUDE.md's Phase 2 plan: "line
    items/totals/payments for an invoice") sorted by id so the digest is
    stable regardless of query row order.

    Args:
        db: Active database session.
        invoice: The invoice to build the payload for — read within the same
            transaction as the write being verified, so it reflects the
            payment/line items already flushed but not yet committed.

    Returns:
        dict: JSON-primitive canonical payload, ready for app.utils.checksum.
    """
    items_result = await db.execute(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice.id)
    )
    items = sorted(items_result.scalars().all(), key=lambda i: str(i.id))

    payments_result = await db.execute(select(Payment).where(Payment.invoice_id == invoice.id))
    payments = payments_result.scalars().all()

    return {
        "invoice_id": str(invoice.id),
        "subtotal_cents": invoice.subtotal_cents,
        "tax_cents": invoice.tax_cents,
        "discount_cents": invoice.discount_cents,
        "total_cents": invoice.total_cents,
        "line_items": [
            {
                "id": str(i.id),
                "product_id": str(i.product_id) if i.product_id else None,
                "quantity": i.quantity,
                "line_total_cents": i.line_total_cents,
            }
            for i in items
        ],
        # Keyed by client_ref (known to the device before the call that
        # creates the row) rather than the server-generated id, so the
        # device can compute this checksum for the payment it is about to
        # submit without needing a round trip first.
        "payments": [
            {"ref": p.client_ref or str(p.id), "method": p.method, "amount_cents": p.amount_cents}
            for p in sorted(payments, key=lambda p: p.client_ref or str(p.id))
        ],
    }


# ── Public service functions ──────────────────────────────────────────────────


async def list_invoices(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
    invoice_status: str | None = None,
) -> list[Invoice]:
    """
    Return invoices for a site ordered by created_at descending.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        site_id: Site to list invoices for.
        skip: Pagination offset.
        limit: Maximum rows to return.
        invoice_status: Optional status filter (e.g. "open" — the Register's
            Held Orders tab lists a site's unpaid-but-line-item-bearing
            invoices this way; add_line_item() moves a DRAFT invoice to OPEN
            once it has a line, so a held order is always status=open).

    Returns:
        list[Invoice]: Invoices ordered most-recent-first.
    """
    query = select(Invoice).where(Invoice.brand_id == brand_id, Invoice.site_id == site_id)
    if invoice_status is not None:
        query = query.where(Invoice.status == invoice_status)
    result = await db.execute(query.order_by(Invoice.created_at.desc()).offset(skip).limit(limit))
    return list(result.scalars().all())


async def get_payment_methods_by_invoice(
    db: AsyncSession, invoice_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """
    Resolve each invoice's distinct payment methods (e.g. ["cash", "card"]
    for a split payment) for a batch of invoices.

    Powers the Register's invoice history list, which shows payment
    method(s) as a per-row column (InvoiceResponse.payment_methods) —
    mirrors invoice_report_service's own payment_methods resolution for the
    management portal's Invoices table, but via a plain query rather than
    that module's raw-SQL view (this module is ORM-only per CLAUDE.md rule 6).

    Args:
        db: Active database session.
        invoice_ids: Invoice ids to resolve payment methods for.

    Returns:
        dict[uuid.UUID, list[str]]: invoice_id -> sorted distinct payment
            methods actually recorded (an id with no payments, e.g. an
            unpaid/held invoice, is simply absent from the dict).
    """
    if not invoice_ids:
        return {}
    result = await db.execute(
        select(Payment.invoice_id, Payment.method)
        .where(Payment.invoice_id.in_(invoice_ids))
        .distinct()
    )
    methods_by_invoice: dict[uuid.UUID, list[str]] = defaultdict(list)
    for invoice_id, method in result.all():
        methods_by_invoice[invoice_id].append(method)
    return {invoice_id: sorted(methods) for invoice_id, methods in methods_by_invoice.items()}


async def list_line_items(
    db: AsyncSession, brand_id: uuid.UUID, invoice_id: uuid.UUID
) -> list[LineItemDetailResponse]:
    """
    Return every line item on an invoice, each with its attached modifiers,
    ordered by display_order.

    Powers the Register's Held Orders recall: reconstructing an on-device
    cart from an invoice that was held (created, lines added, never paid) —
    there was previously no way to fetch a full line-item list for an
    invoice, only one line at a time (get_line_item_detail).

    Args:
        db: Active database session.
        brand_id: Brand scope.
        invoice_id: Invoice to fetch line items for.

    Returns:
        list[LineItemDetailResponse]: Line items with modifiers, ordered by display_order.

    Raises:
        HTTPException: 404 if the invoice does not exist within the brand.
    """
    await _get_invoice_or_404(db, brand_id, invoice_id)
    result = await db.execute(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == invoice_id)
        .order_by(InvoiceLineItem.display_order)
    )
    items = list(result.scalars().all())
    if not items:
        return []

    mods_result = await db.execute(
        select(InvoiceLineModifier).where(
            InvoiceLineModifier.line_item_id.in_([i.id for i in items])
        )
    )
    mods_by_line: dict[uuid.UUID, list[InvoiceLineModifier]] = defaultdict(list)
    for mod in mods_result.scalars().all():
        mods_by_line[mod.line_item_id].append(mod)

    return [
        LineItemDetailResponse(
            **LineItemResponse.model_validate(item).model_dump(),
            modifiers=[LineModifierResponse.model_validate(m) for m in mods_by_line.get(item.id, [])],
        )
        for item in items
    ]


async def create_invoice(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID,
    actor: User,
    register_session_id: uuid.UUID,
    client_ref: str | None = None,
) -> Invoice:
    """
    Create a DRAFT invoice for a site.

    Idempotent when client_ref is supplied: a retried create call that
    already landed (the write succeeded but the device never saw the
    response) returns the original invoice instead of creating a duplicate
    draft.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        site_id: Site the invoice belongs to.
        actor: The authenticated POS user.
        register_session_id: The device's open till session this sale is
            rung up under — callers resolve this via
            register_session_service.get_open_session_or_400() before
            calling create_invoice(), so a sale is never orphaned from a shift.
        client_ref: Optional client-generated idempotency key.

    Returns:
        Invoice: The newly created (or, on a deduped retry, the
            already-existing) draft invoice.
    """
    if client_ref is not None:
        existing_result = await db.execute(select(Invoice).where(Invoice.client_ref == client_ref))
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            log.info("invoice.create.deduped", client_ref=client_ref)
            return existing

    invoice = Invoice(
        id=uuid.uuid4(),
        brand_id=brand_id,
        site_id=site_id,
        created_by_id=actor.id,
        register_session_id=register_session_id,
        invoice_type=InvoiceType.SALE.value,
        status=InvoiceStatus.DRAFT.value,
        client_ref=client_ref,
    )
    db.add(invoice)

    await log_action(
        db=db,
        action=INVOICE_CREATED,
        entity_type="invoice",
        entity_id=str(invoice.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "site_id": str(site_id),
            "status": InvoiceStatus.DRAFT.value,
            "register_session_id": str(register_session_id),
        },
    )

    await db.commit()
    await db.refresh(invoice)
    log.info("invoice.created", invoice_id=str(invoice.id), site_id=str(site_id))
    return invoice


async def add_line_item(
    db: AsyncSession,
    brand_id: uuid.UUID,
    invoice_id: uuid.UUID,
    payload: AddLineItemRequest,
    actor: User,
) -> InvoiceLineItem:
    """
    Add a product as a line item to an invoice.

    Snapshots product_name, unit_price_cents, and tax data at this moment.
    Recomputes invoice totals after insertion.

    Args:
        db: Active database session.
        brand_id: Brand scope for product lookup.
        invoice_id: Invoice to add the line to.
        payload: Line item data.
        actor: The authenticated POS user.

    Returns:
        InvoiceLineItem: The created line item with computed tax values.

    Raises:
        HTTPException: 404 if invoice or product not found within the brand.
        HTTPException: 409 if the invoice is not in an editable state.
    """
    invoice = await _get_invoice_or_404(db, brand_id, invoice_id)

    if invoice.status not in (InvoiceStatus.DRAFT.value, InvoiceStatus.OPEN.value):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot add line items to a paid or voided invoice",
        )

    # Load product — must belong to brand
    prod_result = await db.execute(
        select(Product).where(Product.id == payload.product_id, Product.brand_id == brand_id)
    )
    product = prod_result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Price and tax are NOT computed from rates at sale time. Each product stores
    # a tax-inclusive price and a derived tax-exclusive price; the is_taxable
    # flag picks which is charged. Taxable → inclusive price with GST embedded;
    # not taxable → exclusive price with no tax.
    qty = payload.quantity
    if product.is_taxable:
        unit_price_cents = product.base_price_cents           # inclusive
        subtotal = unit_price_cents * qty
        # GST embedded in the inclusive price = inc − ex, per unit × quantity
        tax_cents = (product.base_price_cents - product.price_ex_cents) * qty
        line_total = subtotal                                  # tax already embedded
        tax_model_snapshot = "inclusive"
        # Effective percent for the receipt, derived from the stored split
        rate_pct = (
            (Decimal(tax_cents) / Decimal(product.price_ex_cents * qty) * Decimal("100"))
            if product.price_ex_cents > 0
            else Decimal("0")
        ).quantize(Decimal("0.0001"))
    else:
        unit_price_cents = product.price_ex_cents             # exclusive, no tax
        subtotal = unit_price_cents * qty
        tax_cents = 0
        line_total = subtotal
        tax_model_snapshot = "exclusive"
        rate_pct = Decimal("0")

    line = InvoiceLineItem(
        id=uuid.uuid4(),
        invoice_id=invoice.id,
        product_id=product.id,
        # ── SNAPSHOT FIELDS ──
        product_name=product.name,
        unit_price_cents=unit_price_cents,
        tax_category_name="Taxable" if product.is_taxable else "Tax free",
        tax_rate_percent=rate_pct,
        tax_model=tax_model_snapshot,
        # ── Computed quantities ──
        quantity=qty,
        subtotal_cents=subtotal,
        tax_cents=tax_cents,
        line_total_cents=line_total,
        display_order=payload.display_order,
        notes=payload.notes,
    )
    db.add(line)
    await db.flush()

    # Record the GST breakdown for the receipt when tax applies. tax_rate_id is
    # NULL — the amount comes from the product's stored inc/ex split, not a
    # brand tax_rates row. taxable_amount is the exclusive (pre-tax) base.
    if tax_cents > 0:
        db.add(
            InvoiceTaxBreakdown(
                id=uuid.uuid4(),
                invoice_id=invoice.id,
                tax_rate_id=None,
                tax_rate_name="Tax",
                rate_percent=rate_pct,
                tax_model=tax_model_snapshot,
                taxable_amount_cents=product.price_ex_cents * qty,
                tax_amount_cents=tax_cents,
            )
        )

    # Recompute invoice totals
    await db.flush()
    await _recompute_invoice_totals(db, invoice)

    # Move invoice to OPEN once it has at least one line item
    if invoice.status == InvoiceStatus.DRAFT.value:
        invoice.status = InvoiceStatus.OPEN.value

    await log_action(
        db=db,
        action=INVOICE_LINE_ITEM_ADDED,
        entity_type="invoice_line_item",
        entity_id=str(line.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "invoice_id": str(invoice.id),
            "product_id": str(product.id),
            "quantity": payload.quantity,
            "subtotal_cents": subtotal,
        },
    )

    await db.commit()
    await db.refresh(line)
    log.info("invoice.line_item.added", line_id=str(line.id), invoice_id=str(invoice.id))
    return line


async def _get_line_item_or_404(
    db: AsyncSession, invoice_id: uuid.UUID, line_item_id: uuid.UUID
) -> InvoiceLineItem:
    """Fetch a line item scoped to its parent invoice, or raise 404."""
    result = await db.execute(
        select(InvoiceLineItem).where(
            InvoiceLineItem.id == line_item_id,
            InvoiceLineItem.invoice_id == invoice_id,
        )
    )
    line = result.scalar_one_or_none()
    if line is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found")
    return line


async def _rebuild_tax_breakdown(db: AsyncSession, invoice: Invoice) -> None:
    """
    Rebuild invoice_tax_breakdowns from the invoice's current line items.

    add_line_item() inserts one breakdown row per taxable line at creation
    time; there is no FK from a breakdown row back to its line item, so a
    quantity change or removal can't surgically patch the matching row.
    Delete-and-reinsert keeps the same one-row-per-taxable-line shape
    add_line_item() already produces, just recomputed from the current set
    of lines instead of appended to incrementally.
    """
    await db.execute(delete(InvoiceTaxBreakdown).where(InvoiceTaxBreakdown.invoice_id == invoice.id))
    items_result = await db.execute(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice.id)
    )
    for item in items_result.scalars().all():
        if item.tax_cents <= 0 or item.quantity <= 0:
            continue
        # taxable_amount_cents = exclusive base = subtotal - tax, for inclusive
        # lines; for exclusive lines tax_cents is 0 so this branch is unreached.
        db.add(
            InvoiceTaxBreakdown(
                id=uuid.uuid4(),
                invoice_id=invoice.id,
                tax_rate_id=None,
                tax_rate_name="Tax",
                rate_percent=item.tax_rate_percent,
                tax_model=item.tax_model,
                taxable_amount_cents=item.subtotal_cents - item.tax_cents,
                tax_amount_cents=item.tax_cents,
            )
        )
    await db.flush()


async def update_line_item_quantity(
    db: AsyncSession,
    brand_id: uuid.UUID,
    invoice_id: uuid.UUID,
    line_item_id: uuid.UUID,
    payload: UpdateLineItemQuantityRequest,
    actor: User,
) -> InvoiceLineItem:
    """
    Change a line item's quantity, rescaling its already-snapshotted per-unit price/tax.

    Never re-fetches the product — per the snapshot rule, unit_price_cents and
    tax_rate_percent/tax_model stay fixed at whatever they were when the line
    was added; only the quantity-derived totals (subtotal_cents, tax_cents,
    line_total_cents) change.

    Args:
        db: Active database session.
        brand_id: Brand scope for the invoice lookup.
        invoice_id: Parent invoice.
        line_item_id: Line item to update.
        payload: The new quantity.
        actor: The authenticated POS user.

    Returns:
        InvoiceLineItem: The updated line item.

    Raises:
        HTTPException: 404 if invoice or line item not found.
        HTTPException: 409 if the invoice is not in an editable state.
    """
    invoice = await _get_invoice_or_404(db, brand_id, invoice_id)

    if invoice.status not in (InvoiceStatus.DRAFT.value, InvoiceStatus.OPEN.value):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot modify line items on a paid or voided invoice",
        )

    line = await _get_line_item_or_404(db, invoice_id, line_item_id)

    # Per-unit tax is constant across quantity changes — tax_cents was
    # computed as (per-unit tax) × (original quantity) at creation, so this
    # division is exact.
    per_unit_tax_cents = line.tax_cents // line.quantity if line.quantity else 0
    before_quantity = line.quantity

    line.quantity = payload.quantity
    line.subtotal_cents = line.unit_price_cents * payload.quantity
    line.tax_cents = per_unit_tax_cents * payload.quantity
    line.line_total_cents = line.subtotal_cents  # tax is embedded for both models, per add_line_item

    await db.flush()
    await _rebuild_tax_breakdown(db, invoice)
    await _recompute_invoice_totals(db, invoice)

    await log_action(
        db=db,
        action=INVOICE_LINE_ITEM_QUANTITY_UPDATED,
        entity_type="invoice_line_item",
        entity_id=str(line.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"quantity": before_quantity},
        after_state={"quantity": payload.quantity},
    )

    await db.commit()
    await db.refresh(line)
    log.info("invoice.line_item.quantity_updated", line_id=str(line.id), quantity=payload.quantity)
    return line


async def remove_line_item(
    db: AsyncSession,
    brand_id: uuid.UUID,
    invoice_id: uuid.UUID,
    line_item_id: uuid.UUID,
    actor: User,
) -> None:
    """
    Remove a line item from an invoice and recompute totals.

    Args:
        db: Active database session.
        brand_id: Brand scope for the invoice lookup.
        invoice_id: Parent invoice.
        line_item_id: Line item to remove.
        actor: The authenticated POS user.

    Raises:
        HTTPException: 404 if invoice or line item not found.
        HTTPException: 409 if the invoice is not in an editable state.
    """
    invoice = await _get_invoice_or_404(db, brand_id, invoice_id)

    if invoice.status not in (InvoiceStatus.DRAFT.value, InvoiceStatus.OPEN.value):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot modify line items on a paid or voided invoice",
        )

    line = await _get_line_item_or_404(db, invoice_id, line_item_id)
    removed_state = {"product_name": line.product_name, "quantity": line.quantity}

    # Modifiers cascade via invoice_line_modifiers.line_item_id ON DELETE CASCADE.
    await db.delete(line)
    await db.flush()
    await _rebuild_tax_breakdown(db, invoice)
    await _recompute_invoice_totals(db, invoice)

    await log_action(
        db=db,
        action=INVOICE_LINE_ITEM_REMOVED,
        entity_type="invoice_line_item",
        entity_id=str(line_item_id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=removed_state,
    )

    await db.commit()
    log.info("invoice.line_item.removed", line_id=str(line_item_id), invoice_id=str(invoice_id))


async def add_line_modifier(
    db: AsyncSession,
    brand_id: uuid.UUID,
    invoice_id: uuid.UUID,
    line_item_id: uuid.UUID,
    payload: AddModifierRequest,
    actor: User,
) -> InvoiceLineModifier:
    """
    Attach a modifier selection to an invoice line item.

    Snapshots modifier_name and price_delta_cents. Recomputes invoice totals.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        invoice_id: Parent invoice.
        line_item_id: Line item to attach the modifier to.
        payload: Modifier option to attach.
        actor: The authenticated POS user.

    Returns:
        InvoiceLineModifier: The created modifier row.

    Raises:
        HTTPException: 404 if invoice, line item, or modifier option not found.
        HTTPException: 409 if invoice is not editable.
    """
    invoice = await _get_invoice_or_404(db, brand_id, invoice_id)

    if invoice.status not in (InvoiceStatus.DRAFT.value, InvoiceStatus.OPEN.value):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot modify a paid or voided invoice",
        )

    # Verify the line item belongs to this invoice
    li_result = await db.execute(
        select(InvoiceLineItem).where(
            InvoiceLineItem.id == line_item_id,
            InvoiceLineItem.invoice_id == invoice_id,
        )
    )
    line_item = li_result.scalar_one_or_none()
    if line_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found")

    # Load modifier option — snapshot its name and price delta
    opt_result = await db.execute(
        select(ModifierOption).where(ModifierOption.id == payload.modifier_option_id)
    )
    option = opt_result.scalar_one_or_none()
    if option is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Modifier option not found"
        )

    modifier = InvoiceLineModifier(
        id=uuid.uuid4(),
        line_item_id=line_item_id,
        modifier_option_id=option.id,
        # ── SNAPSHOT FIELDS ──
        modifier_name=option.name,
        price_delta_cents=option.price_delta_cents,
    )
    db.add(modifier)
    await db.flush()

    # Recompute invoice totals (modifier price_delta affects total)
    await _recompute_invoice_totals(db, invoice)

    await log_action(
        db=db,
        action=INVOICE_LINE_ITEM_MODIFIER_ADDED,
        entity_type="invoice_line_item",
        entity_id=str(line_item_id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "modifier_option_id": str(option.id),
            "modifier_name": option.name,
            "price_delta_cents": option.price_delta_cents,
        },
    )

    await db.commit()
    await db.refresh(modifier)
    log.info("invoice.modifier.added", modifier_id=str(modifier.id))
    return modifier


async def get_line_item_detail(
    db: AsyncSession,
    brand_id: uuid.UUID,
    invoice_id: uuid.UUID,
    line_item_id: uuid.UUID,
) -> LineItemDetailResponse:
    """
    Fetch a single line item with its currently attached modifiers.

    Used by the POS Register screen to refresh a line's display state (its
    "· modifier" sub-lines and modifier-inclusive total) right after
    attaching one or more modifiers via add_line_modifier(), which itself
    only returns the created modifier row.

    Args:
        db: Active database session.
        brand_id: Brand scope for the invoice lookup.
        invoice_id: Parent invoice.
        line_item_id: Line item to fetch.

    Returns:
        LineItemDetailResponse: The line item plus its attached modifiers.

    Raises:
        HTTPException: 404 if the invoice or line item is not found.
    """
    await _get_invoice_or_404(db, brand_id, invoice_id)
    line = await _get_line_item_or_404(db, invoice_id, line_item_id)

    mods_result = await db.execute(
        select(InvoiceLineModifier)
        .where(InvoiceLineModifier.line_item_id == line.id)
        .order_by(InvoiceLineModifier.created_at)
    )
    modifiers = list(mods_result.scalars().all())

    return LineItemDetailResponse(
        **LineItemResponse.model_validate(line).model_dump(),
        modifiers=[LineModifierResponse.model_validate(m) for m in modifiers],
    )


async def apply_discount(
    db: AsyncSession,
    brand_id: uuid.UUID,
    invoice_id: uuid.UUID,
    payload: ApplyDiscountRequest,
    actor: User,
) -> Invoice:
    """
    Apply a flat discount to an invoice.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        invoice_id: Invoice to discount.
        payload: discount_cents and optional reason.
        actor: The authenticated POS user.

    Returns:
        Invoice: The updated invoice with new totals.

    Raises:
        HTTPException: 404 if invoice not found.
        HTTPException: 409 if invoice is not editable.
    """
    invoice = await _get_invoice_or_404(db, brand_id, invoice_id)

    if invoice.status not in (InvoiceStatus.DRAFT.value, InvoiceStatus.OPEN.value):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot discount a paid or voided invoice",
        )

    before = {"discount_cents": invoice.discount_cents}
    invoice.discount_cents = payload.discount_cents
    invoice.discount_reason = payload.reason

    await _recompute_invoice_totals(db, invoice)

    await log_action(
        db=db,
        action=INVOICE_DISCOUNT_APPLIED,
        entity_type="invoice",
        entity_id=str(invoice.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state={"discount_cents": payload.discount_cents, "reason": payload.reason},
    )

    await db.commit()
    await db.refresh(invoice)
    return invoice


async def pay_invoice(
    db: AsyncSession,
    brand_id: uuid.UUID,
    invoice_id: uuid.UUID,
    payload: PayInvoiceRequest,
    actor: User,
) -> Invoice:
    """
    Record a payment against an invoice.

    The invoice is marked PAID once the sum of all its payments (this one
    included) covers total_cents — matching the Payment model's own
    documented contract. A payment smaller than the remaining balance
    records the leg and leaves the invoice OPEN so a caller can submit
    further legs of a split payment; the invoice status in the response
    tells the caller whether the balance is now fully covered.

    Idempotent when payload.client_ref is supplied: a retried pay call that
    already landed (a Payment row already exists with that client_ref)
    returns the invoice's current state instead of recording a duplicate
    payment leg.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        invoice_id: Invoice to pay.
        payload: Payment method, amount, and optional idempotency key / checksum.
        actor: The authenticated POS user.

    Returns:
        Invoice: The updated invoice — status is only "paid" once the sum of
            all payments covers total_cents.

    Raises:
        HTTPException: 404 if invoice not found.
        HTTPException: 409 if already paid or voided.
        HTTPException: 422 if payload.checksum is supplied and doesn't
            match the server's own computed checksum over the invoice's
            line items, totals, and payments after this one is applied.
    """
    invoice = await _get_invoice_or_404(db, brand_id, invoice_id)

    if payload.client_ref is not None:
        existing_payment_result = await db.execute(
            select(Payment).where(Payment.client_ref == payload.client_ref)
        )
        if existing_payment_result.scalar_one_or_none() is not None:
            log.info("invoice.pay.deduped", client_ref=payload.client_ref)
            return invoice

    if invoice.status == InvoiceStatus.PAID.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invoice is already paid",
        )
    if invoice.status == InvoiceStatus.VOIDED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot pay a voided invoice",
        )

    now = datetime.now(tz=timezone.utc)

    payment = Payment(
        id=uuid.uuid4(),
        invoice_id=invoice.id,
        method=payload.method,
        amount_cents=payload.amount_cents,
        reference=payload.reference,
        paid_at=now,
        client_ref=payload.client_ref,
    )
    db.add(payment)
    await db.flush()

    # Sum every payment recorded against this invoice so far (this one
    # included) — a split payment is only "paid" once the cumulative total
    # covers the invoice, not on the first leg regardless of amount.
    paid_result = await db.execute(
        select(func.sum(Payment.amount_cents)).where(Payment.invoice_id == invoice.id)
    )
    # SUM() over a BigInteger column types as Numeric, so asyncpg returns a
    # Decimal here — cast to int (money is always cents, never fractional)
    # so it JSON-serializes cleanly into the audit log's after_state.
    total_paid_cents = int(paid_result.scalar_one() or 0)
    fully_paid = total_paid_cents >= invoice.total_cents

    checksum = verify_checksum(await _build_invoice_checksum_payload(db, invoice), payload.checksum)
    invoice.checksum = checksum

    if fully_paid:
        invoice.status = InvoiceStatus.PAID.value
        invoice.paid_at = now

    await log_action(
        db=db,
        action=INVOICE_PAID if fully_paid else INVOICE_PAYMENT_RECORDED,
        entity_type="invoice",
        entity_id=str(invoice.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "method": payload.method,
            "amount_cents": payload.amount_cents,
            "total_paid_cents": total_paid_cents,
            "total_cents": invoice.total_cents,
            "fully_paid": fully_paid,
        },
    )

    await db.commit()
    await db.refresh(invoice)
    log.info(
        "invoice.paid" if fully_paid else "invoice.payment_leg_recorded",
        invoice_id=str(invoice.id),
        amount_cents=payload.amount_cents,
        fully_paid=fully_paid,
    )
    return invoice


async def void_invoice(
    db: AsyncSession,
    brand_id: uuid.UUID,
    invoice_id: uuid.UUID,
    actor: User,
) -> Invoice:
    """
    Void an invoice.

    Cannot void a PAID invoice (use refund instead).

    Args:
        db: Active database session.
        brand_id: Brand scope.
        invoice_id: Invoice to void.
        actor: The authenticated POS user.

    Returns:
        Invoice: The voided invoice.

    Raises:
        HTTPException: 404 if not found.
        HTTPException: 409 if already voided or paid.
    """
    invoice = await _get_invoice_or_404(db, brand_id, invoice_id)

    if invoice.status == InvoiceStatus.VOIDED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invoice is already voided",
        )
    if invoice.status == InvoiceStatus.PAID.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot void a paid invoice — use refund instead",
        )

    now = datetime.now(tz=timezone.utc)
    invoice.status = InvoiceStatus.VOIDED.value
    invoice.voided_at = now

    await log_action(
        db=db,
        action=INVOICE_VOIDED,
        entity_type="invoice",
        entity_id=str(invoice.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"status": InvoiceStatus.OPEN.value},
        after_state={"status": InvoiceStatus.VOIDED.value},
    )

    await db.commit()
    await db.refresh(invoice)
    log.info("invoice.voided", invoice_id=str(invoice.id))
    return invoice


async def create_refund(
    db: AsyncSession,
    brand_id: uuid.UUID,
    invoice_id: uuid.UUID,
    payload: RefundRequest,
    actor: User,
    register_session_id: uuid.UUID | None,
) -> Invoice:
    """
    Create a refund invoice for a paid invoice — full, or partial by line item.

    The refund invoice is created with status=PAID and invoice_type=REFUND.
    The original invoice is marked is_refunded=True regardless of whether
    this refund was full or partial — there is no per-line refunded-amount
    tracking on InvoiceLineItem, so a second refund against the same
    invoice (even for a disjoint set of items) is blocked to avoid silently
    double-refunding a line. A manager needing to refund more of the same
    invoice later must void/reissue rather than layering partial refunds.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        invoice_id: The original paid invoice to refund.
        payload: Optional reason, and optionally line_item_ids for a
            partial (by-item) refund — see RefundRequest's doc.
        actor: The authenticated POS user.
        register_session_id: The device's currently open till session — a
            refund is attributed to whichever shift processes it, not the
            original sale's session (that may be a different day entirely).
            None when the refund is initiated from the management portal
            (no till session applies there — see routes/invoice_reports.py).

    Returns:
        Invoice: The newly created refund invoice.

    Raises:
        HTTPException: 404 if original invoice not found.
        HTTPException: 400 if line_item_ids is supplied but matches no line
            items on the original invoice.
        HTTPException: 409 if original invoice is not paid or already refunded.
    """
    original = await _get_invoice_or_404(db, brand_id, invoice_id)

    if original.status != InvoiceStatus.PAID.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Can only refund a paid invoice",
        )
    if original.is_refunded:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invoice has already been refunded",
        )

    if payload.line_item_ids:
        items_result = await db.execute(
            select(InvoiceLineItem).where(
                InvoiceLineItem.invoice_id == original.id,
                InvoiceLineItem.id.in_(payload.line_item_ids),
            )
        )
        items = items_result.scalars().all()
        if not items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No matching line items found for a partial refund",
            )
        mods_result = await db.execute(
            select(InvoiceLineModifier).where(
                InvoiceLineModifier.line_item_id.in_([i.id for i in items])
            )
        )
        modifier_total = sum(m.price_delta_cents for m in mods_result.scalars().all())
        refund_subtotal = sum(i.subtotal_cents for i in items) + modifier_total
        refund_tax = sum(i.tax_cents for i in items)
        refund_total = sum(i.line_total_cents for i in items) + modifier_total
    else:
        refund_subtotal = original.subtotal_cents
        refund_tax = original.tax_cents
        refund_total = original.total_cents

    now = datetime.now(tz=timezone.utc)

    refund = Invoice(
        id=uuid.uuid4(),
        brand_id=brand_id,
        site_id=original.site_id,
        created_by_id=actor.id,
        register_session_id=register_session_id,
        invoice_type=InvoiceType.REFUND.value,
        status=InvoiceStatus.PAID.value,
        subtotal_cents=-refund_subtotal,
        tax_cents=-refund_tax,
        discount_cents=0,
        discount_reason=payload.reason,
        total_cents=-refund_total,
        refund_of_id=original.id,
        paid_at=now,
    )
    db.add(refund)

    # Mark the original as refunded
    original.is_refunded = True

    await log_action(
        db=db,
        action=INVOICE_REFUNDED,
        entity_type="invoice",
        entity_id=str(refund.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "refund_of_id": str(original.id),
            "total_cents": refund.total_cents,
        },
    )
    # Also log against the original invoice's own entity_id — its change-log
    # panel (Stage 21) reads audit_logs by entity_id, and a refund is only
    # ever written above against the *new* refund invoice's id, which would
    # otherwise leave the original invoice's timeline silent about it.
    await log_action(
        db=db,
        action=INVOICE_REFUNDED,
        entity_type="invoice",
        entity_id=str(original.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_refunded": False},
        after_state={"is_refunded": True, "refund_invoice_id": str(refund.id)},
    )

    await db.commit()
    await db.refresh(refund)
    log.info("invoice.refunded", refund_id=str(refund.id), original_id=str(original.id))
    return refund
