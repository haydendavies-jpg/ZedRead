"""Invoice routes — create, add line items, pay, void, and refund invoices."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.invoice_service import (
    AddLineItemRequest,
    AddModifierRequest,
    ApplyDiscountRequest,
    InvoiceResponse,
    LineItemResponse,
    LineModifierResponse,
    PayInvoiceRequest,
    RefundRequest,
    add_line_item,
    add_line_modifier,
    apply_discount,
    create_invoice,
    create_refund,
    list_invoices,
    pay_invoice,
    void_invoice,
)
from app.utils.dependencies import POSAccess, resolve_access

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("", response_model=list[InvoiceResponse], status_code=status.HTTP_200_OK)
async def list_site_invoices(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> list[InvoiceResponse]:
    """
    List invoices for the authenticated user's site (most recent first).

    Args:
        skip: Pagination offset.
        limit: Maximum invoices to return.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        list[InvoiceResponse]: Invoices for the site.
    """
    invoices = await list_invoices(db, access.user.brand_id, access.site.id, skip, limit)
    return [InvoiceResponse.model_validate(inv) for inv in invoices]


@router.post("", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_site_invoice(
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> InvoiceResponse:
    """
    Create a draft invoice for the authenticated user's site.

    Args:
        access: Resolved POS access.
        db: Active database session.

    Returns:
        InvoiceResponse: The newly created draft invoice.
    """
    invoice = await create_invoice(db, access.user.brand_id, access.site.id, access.user)
    return InvoiceResponse.model_validate(invoice)


@router.get(
    "/{invoice_id}", response_model=InvoiceResponse, status_code=status.HTTP_200_OK
)
async def get_invoice(
    invoice_id: uuid.UUID,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> InvoiceResponse:
    """
    Fetch a single invoice by ID.

    Args:
        invoice_id: UUID of the invoice.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        InvoiceResponse: The invoice.
    """
    from app.services.invoice_service import _get_invoice_or_404

    invoice = await _get_invoice_or_404(db, access.user.brand_id, invoice_id)
    return InvoiceResponse.model_validate(invoice)


@router.post(
    "/{invoice_id}/line-items",
    response_model=LineItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_invoice_line_item(
    invoice_id: uuid.UUID,
    payload: AddLineItemRequest,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> LineItemResponse:
    """
    Add a product as a line item to an invoice.

    Snapshots product name, price, and tax data at this moment.

    Args:
        invoice_id: UUID of the invoice to add the line to.
        payload: Product and quantity data.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        LineItemResponse: The created line item with computed tax values.
    """
    line = await add_line_item(db, access.user.brand_id, invoice_id, payload, access.user)
    return LineItemResponse.model_validate(line)


@router.post(
    "/{invoice_id}/line-items/{line_item_id}/modifiers",
    response_model=LineModifierResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_invoice_line_modifier(
    invoice_id: uuid.UUID,
    line_item_id: uuid.UUID,
    payload: AddModifierRequest,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> LineModifierResponse:
    """
    Attach a modifier option to a line item.

    Args:
        invoice_id: UUID of the parent invoice.
        line_item_id: UUID of the line item to attach the modifier to.
        payload: Modifier option ID.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        LineModifierResponse: The created modifier row.
    """
    modifier = await add_line_modifier(
        db, access.user.brand_id, invoice_id, line_item_id, payload, access.user
    )
    return LineModifierResponse.model_validate(modifier)


@router.post(
    "/{invoice_id}/discount",
    response_model=InvoiceResponse,
    status_code=status.HTTP_200_OK,
)
async def apply_invoice_discount(
    invoice_id: uuid.UUID,
    payload: ApplyDiscountRequest,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> InvoiceResponse:
    """
    Apply a flat discount to an invoice.

    Args:
        invoice_id: UUID of the invoice to discount.
        payload: Discount amount and optional reason.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        InvoiceResponse: The updated invoice.
    """
    invoice = await apply_discount(db, access.user.brand_id, invoice_id, payload, access.user)
    return InvoiceResponse.model_validate(invoice)


@router.post(
    "/{invoice_id}/pay",
    response_model=InvoiceResponse,
    status_code=status.HTTP_200_OK,
)
async def pay_site_invoice(
    invoice_id: uuid.UUID,
    payload: PayInvoiceRequest,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> InvoiceResponse:
    """
    Record a payment against an invoice.

    Args:
        invoice_id: UUID of the invoice to pay.
        payload: Payment method and amount.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        InvoiceResponse: The updated invoice with status=paid.
    """
    invoice = await pay_invoice(db, access.user.brand_id, invoice_id, payload, access.user)
    return InvoiceResponse.model_validate(invoice)


@router.post(
    "/{invoice_id}/void",
    response_model=InvoiceResponse,
    status_code=status.HTTP_200_OK,
)
async def void_site_invoice(
    invoice_id: uuid.UUID,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> InvoiceResponse:
    """
    Void an invoice (cannot void a paid invoice).

    Args:
        invoice_id: UUID of the invoice to void.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        InvoiceResponse: The voided invoice.
    """
    invoice = await void_invoice(db, access.user.brand_id, invoice_id, access.user)
    return InvoiceResponse.model_validate(invoice)


@router.post(
    "/{invoice_id}/refund",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def refund_site_invoice(
    invoice_id: uuid.UUID,
    payload: RefundRequest,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> InvoiceResponse:
    """
    Create a refund invoice for a paid invoice.

    Args:
        invoice_id: UUID of the original invoice to refund.
        payload: Optional reason.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        InvoiceResponse: The newly created refund invoice.
    """
    refund = await create_refund(db, access.user.brand_id, invoice_id, payload, access.user)
    return InvoiceResponse.model_validate(refund)
