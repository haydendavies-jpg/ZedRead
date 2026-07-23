"""Invoice routes — create, add line items, pay, void, and refund invoices."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.invoice_service import (
    AddLineItemRequest,
    AddModifierRequest,
    ApplyDiscountRequest,
    InvoiceCreateRequest,
    InvoiceResponse,
    LineItemDetailResponse,
    LineItemResponse,
    LineModifierResponse,
    PayInvoiceRequest,
    RefundRequest,
    UpdateLineItemQuantityRequest,
    add_line_item,
    add_line_modifier,
    apply_discount,
    create_invoice,
    create_refund,
    get_line_item_detail,
    list_invoices,
    list_line_items,
    pay_invoice,
    remove_line_item,
    update_line_item_quantity,
    void_invoice,
)
from app.services.register_session_service import get_open_session_or_400
from app.utils.dependencies import POSAccess, resolve_access

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("", response_model=list[InvoiceResponse], status_code=status.HTTP_200_OK)
async def list_site_invoices(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    invoice_status: str | None = Query(None, alias="status", description="Optional status filter, e.g. 'open' for held orders"),
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> list[InvoiceResponse]:
    """
    List invoices for the authenticated user's site (most recent first).

    Args:
        skip: Pagination offset.
        limit: Maximum invoices to return.
        invoice_status: Optional status filter — the Register's Held Orders
            tab passes status=open to list unpaid, line-item-bearing invoices.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        list[InvoiceResponse]: Invoices for the site.
    """
    invoices = await list_invoices(db, access.user.brand_id, access.site.id, skip, limit, invoice_status)
    return [InvoiceResponse.model_validate(inv) for inv in invoices]


@router.get(
    "/{invoice_id}/line-items",
    response_model=list[LineItemDetailResponse],
    status_code=status.HTTP_200_OK,
)
async def list_invoice_line_items(
    invoice_id: uuid.UUID,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> list[LineItemDetailResponse]:
    """
    Fetch every line item on an invoice, each with its attached modifiers.

    Powers the Register's Held Orders recall — reconstructing an on-device
    cart from a held (line items added, never paid) invoice.

    Args:
        invoice_id: UUID of the invoice.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        list[LineItemDetailResponse]: The invoice's line items, in order.
    """
    return await list_line_items(db, access.user.brand_id, invoice_id)


@router.post("", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_site_invoice(
    payload: InvoiceCreateRequest = InvoiceCreateRequest(),
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> InvoiceResponse:
    """
    Create a draft invoice for the authenticated user's site.

    Requires an open register session for this terminal — see
    register_session_service.get_open_session_or_400(). Idempotent when
    payload.client_ref is supplied — see create_invoice().

    Args:
        payload: Optional offline-sync idempotency key.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        InvoiceResponse: The newly created (or deduped) draft invoice.

    Raises:
        HTTPException: 400 if no register session is open for this device.
    """
    session = await get_open_session_or_400(db, access.device)
    invoice = await create_invoice(
        db, access.user.brand_id, access.site.id, access.user, session.id, payload.client_ref
    )
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


@router.get(
    "/{invoice_id}/line-items/{line_item_id}",
    response_model=LineItemDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_invoice_line_item(
    invoice_id: uuid.UUID,
    line_item_id: uuid.UUID,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> LineItemDetailResponse:
    """
    Fetch a single line item with its currently attached modifiers.

    The Register screen's modifier customise sheet calls this after
    attaching one or more modifiers to a freshly-added line, to refresh the
    order pane's display (modifier sub-lines and modifier-inclusive total) —
    POST .../modifiers itself only returns the created modifier row, not the
    parent line.

    Args:
        invoice_id: UUID of the parent invoice.
        line_item_id: UUID of the line item to fetch.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        LineItemDetailResponse: The line item plus its attached modifiers.
    """
    return await get_line_item_detail(db, access.user.brand_id, invoice_id, line_item_id)


@router.patch(
    "/{invoice_id}/line-items/{line_item_id}",
    response_model=LineItemResponse,
    status_code=status.HTTP_200_OK,
)
async def update_invoice_line_item_quantity(
    invoice_id: uuid.UUID,
    line_item_id: uuid.UUID,
    payload: UpdateLineItemQuantityRequest,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> LineItemResponse:
    """
    Change a line item's quantity — e.g. the Register screen's qty stepper.

    Args:
        invoice_id: UUID of the parent invoice.
        line_item_id: UUID of the line item to update.
        payload: The new quantity.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        LineItemResponse: The updated line item.
    """
    line = await update_line_item_quantity(
        db, access.user.brand_id, invoice_id, line_item_id, payload, access.user
    )
    return LineItemResponse.model_validate(line)


@router.delete(
    "/{invoice_id}/line-items/{line_item_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_invoice_line_item(
    invoice_id: uuid.UUID,
    line_item_id: uuid.UUID,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove a line item from an invoice — e.g. the Register screen's remove-item action.

    Args:
        invoice_id: UUID of the parent invoice.
        line_item_id: UUID of the line item to remove.
        access: Resolved POS access.
        db: Active database session.
    """
    await remove_line_item(db, access.user.brand_id, invoice_id, line_item_id, access.user)


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

    Raises:
        HTTPException: 400 if no register session is open for this device.
    """
    session = await get_open_session_or_400(db, access.device)
    refund = await create_refund(
        db, access.user.brand_id, invoice_id, payload, access.user, session.id
    )
    return InvoiceResponse.model_validate(refund)
