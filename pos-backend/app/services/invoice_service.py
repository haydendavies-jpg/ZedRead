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

log = structlog.get_logger(__name__)


# ── Inline Pydantic schemas ───────────────────────────────────────────────────

from decimal import Decimal

from pydantic import BaseModel, Field


class InvoiceResponse(BaseModel):
    """Response schema for an invoice."""

    id: uuid.UUID
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


class PayInvoiceRequest(BaseModel):
    """Payload for recording a payment."""

    method: str = Field(..., pattern="^(cash|card|voucher)$")
    amount_cents: int = Field(..., ge=1)
    reference: str | None = None


class RefundRequest(BaseModel):
    """Payload for creating a refund invoice."""

    reason: str | None = None


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


# ── Public service functions ──────────────────────────────────────────────────


async def list_invoices(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
) -> list[Invoice]:
    """
    Return invoices for a site ordered by created_at descending.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        site_id: Site to list invoices for.
        skip: Pagination offset.
        limit: Maximum rows to return.

    Returns:
        list[Invoice]: Invoices ordered most-recent-first.
    """
    result = await db.execute(
        select(Invoice)
        .where(Invoice.brand_id == brand_id, Invoice.site_id == site_id)
        .order_by(Invoice.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def create_invoice(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID,
    actor: User,
    register_session_id: uuid.UUID,
) -> Invoice:
    """
    Create a DRAFT invoice for a site.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        site_id: Site the invoice belongs to.
        actor: The authenticated POS user.
        register_session_id: The device's open till session this sale is
            rung up under — callers resolve this via
            register_session_service.get_open_session_or_400() before
            calling create_invoice(), so a sale is never orphaned from a shift.

    Returns:
        Invoice: The newly created draft invoice.
    """
    invoice = Invoice(
        id=uuid.uuid4(),
        brand_id=brand_id,
        site_id=site_id,
        created_by_id=actor.id,
        register_session_id=register_session_id,
        invoice_type=InvoiceType.SALE.value,
        status=InvoiceStatus.DRAFT.value,
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

    Args:
        db: Active database session.
        brand_id: Brand scope.
        invoice_id: Invoice to pay.
        payload: Payment method and amount.
        actor: The authenticated POS user.

    Returns:
        Invoice: The updated invoice — status is only "paid" once the sum of
            all payments covers total_cents.

    Raises:
        HTTPException: 404 if invoice not found.
        HTTPException: 409 if already paid or voided.
    """
    invoice = await _get_invoice_or_404(db, brand_id, invoice_id)

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
    register_session_id: uuid.UUID,
) -> Invoice:
    """
    Create a refund invoice for a paid invoice.

    The refund invoice is created with status=PAID and invoice_type=REFUND.
    The original invoice is marked is_refunded=True.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        invoice_id: The original paid invoice to refund.
        payload: Optional reason.
        actor: The authenticated POS user.
        register_session_id: The device's currently open till session — a
            refund is attributed to whichever shift processes it, not the
            original sale's session (that may be a different day entirely).

    Returns:
        Invoice: The newly created refund invoice.

    Raises:
        HTTPException: 404 if original invoice not found.
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

    now = datetime.now(tz=timezone.utc)

    refund = Invoice(
        id=uuid.uuid4(),
        brand_id=brand_id,
        site_id=original.site_id,
        created_by_id=actor.id,
        register_session_id=register_session_id,
        invoice_type=InvoiceType.REFUND.value,
        status=InvoiceStatus.PAID.value,
        subtotal_cents=-original.subtotal_cents,
        tax_cents=-original.tax_cents,
        discount_cents=0,
        discount_reason=payload.reason,
        total_cents=-original.total_cents,
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
