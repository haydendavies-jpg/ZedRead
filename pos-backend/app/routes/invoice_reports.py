"""Invoice reporting routes (Stage 21) — filtered list, XLSX export, detail
view, PDF export, and change log.

Read-only and reporting-scoped: the transactional invoice engine (create,
pay, void, refund) lives in routes/invoices.py and is unaffected by this file.
"""

import asyncio
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import export_service
from app.services.invoice_pdf_service import render_invoice_pdf
from app.services.invoice_report_service import (
    ChangeLogEntry,
    InvoiceDetailResponse,
    InvoiceReportRow,
    get_invoice_change_log,
    get_invoice_detail,
    get_invoice_site_id,
    list_invoice_reports,
)
from app.services.invoice_service import InvoiceResponse, RefundRequest, create_refund
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(prefix="/invoice-reports", tags=["invoice-reports"])

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _resolve_site_filter(access: CatalogAccess, site_id: uuid.UUID | None) -> uuid.UUID | None:
    """
    Resolve the effective site filter for a list/export request.

    POS terminal users and site-scope management users are pinned to their
    own site: an explicit site_id must match it, and an absent one defaults
    to it. Brand-scope, group-scope, and portal admin callers may filter by
    any site_id, or supply none to mean "every site in the brand".

    Args:
        access: The resolved catalog access context.
        site_id: The site_id query parameter, if supplied.

    Returns:
        uuid.UUID | None: The site_id to filter by, or None for "all sites".

    Raises:
        HTTPException: 403 if a POS/site-scope caller requests a different site.
    """
    own_site_id: uuid.UUID | None = None
    if access.pos_access:
        own_site_id = access.pos_access.site.id
    elif access.mgmt_access and access.mgmt_access.scope == "site" and access.mgmt_access.site:
        own_site_id = access.mgmt_access.site.id

    if own_site_id is None:
        return site_id
    if site_id is not None and site_id != own_site_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: report scope exceeds your site",
        )
    return own_site_id


def _assert_site_visible(access: CatalogAccess, invoice_site_id: uuid.UUID) -> None:
    """
    Raise 403 if a POS/site-scope caller is looking at an invoice from another site.

    Args:
        access: The resolved catalog access context.
        invoice_site_id: The site_id the invoice belongs to.

    Raises:
        HTTPException: 403 if the invoice's site does not match the caller's own site.
    """
    own_site_id: uuid.UUID | None = None
    if access.pos_access:
        own_site_id = access.pos_access.site.id
    elif access.mgmt_access and access.mgmt_access.scope == "site" and access.mgmt_access.site:
        own_site_id = access.mgmt_access.site.id

    if own_site_id is not None and own_site_id != invoice_site_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: report scope exceeds your site",
        )


@router.get("", response_model=list[InvoiceReportRow], status_code=status.HTTP_200_OK)
async def list_invoices_report(
    site_id: uuid.UUID | None = Query(None, description="Filter by site"),
    start_date: date | None = Query(None, description="Lower bound on invoice date (inclusive)"),
    end_date: date | None = Query(None, description="Upper bound on invoice date (inclusive)"),
    invoice_status: str | None = Query(None, alias="status", description="draft/open/paid/voided"),
    min_amount_cents: int | None = Query(None, ge=0),
    max_amount_cents: int | None = Query(None, ge=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[InvoiceReportRow]:
    """
    List invoices for the authenticated user's brand, filtered and most recent first.

    Args:
        site_id: Optional site filter.
        start_date: Optional lower bound on the invoice date (inclusive).
        end_date: Optional upper bound on the invoice date (inclusive).
        invoice_status: Optional invoice status filter.
        min_amount_cents: Optional lower bound on total_cents.
        max_amount_cents: Optional upper bound on total_cents.
        skip: Pagination offset.
        limit: Maximum invoices to return.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        list[InvoiceReportRow]: Matching invoices ordered by created_at descending.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    effective_site_id = _resolve_site_filter(access, site_id)
    return await list_invoice_reports(
        db,
        effective_brand_id,
        effective_site_id,
        start_date,
        end_date,
        invoice_status,
        min_amount_cents,
        max_amount_cents,
        skip,
        limit,
    )


@router.get("/export", response_model=None, status_code=status.HTTP_200_OK)
async def export_invoices_report(
    site_id: uuid.UUID | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    invoice_status: str | None = Query(None, alias="status"),
    min_amount_cents: int | None = Query(None, ge=0),
    max_amount_cents: int | None = Query(None, ge=0),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Download the filtered invoice set as a .xlsx file — same filters as the list route.

    response_model is intentionally omitted — the body is a binary .xlsx file,
    not a JSON payload a Pydantic model could describe.

    Args:
        site_id: Optional site filter.
        start_date: Optional lower bound on the invoice date (inclusive).
        end_date: Optional upper bound on the invoice date (inclusive).
        invoice_status: Optional invoice status filter.
        min_amount_cents: Optional lower bound on total_cents.
        max_amount_cents: Optional upper bound on total_cents.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        Response: The .xlsx export file.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    effective_site_id = _resolve_site_filter(access, site_id)
    wb = await export_service.build_invoices_export(
        db,
        effective_brand_id,
        effective_site_id,
        start_date,
        end_date,
        invoice_status,
        min_amount_cents,
        max_amount_cents,
    )
    return Response(
        content=export_service.workbook_to_bytes(wb),
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=invoices_export.xlsx"},
    )


@router.get(
    "/{invoice_id}", response_model=InvoiceDetailResponse, status_code=status.HTTP_200_OK
)
async def get_invoice_report_detail(
    invoice_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> InvoiceDetailResponse:
    """
    Full invoice detail: line items with modifiers, tax breakdown, and payments.

    Args:
        invoice_id: UUID of the invoice.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        InvoiceDetailResponse: The assembled invoice detail.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    detail = await get_invoice_detail(db, effective_brand_id, invoice_id)
    _assert_site_visible(access, detail.site_id)
    return detail


@router.get(
    "/{invoice_id}/change-log",
    response_model=list[ChangeLogEntry],
    status_code=status.HTTP_200_OK,
)
async def get_invoice_report_change_log(
    invoice_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[ChangeLogEntry]:
    """
    Audit trail for one invoice — every audit_logs row recorded against it, oldest first.

    Args:
        invoice_id: UUID of the invoice.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        list[ChangeLogEntry]: Audit rows ordered by created_at ascending.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    site_id = await get_invoice_site_id(db, effective_brand_id, invoice_id)
    _assert_site_visible(access, site_id)
    return await get_invoice_change_log(db, effective_brand_id, invoice_id)


@router.get("/{invoice_id}/pdf", response_model=None, status_code=status.HTTP_200_OK)
async def export_invoice_pdf(
    invoice_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Download a standard single-invoice PDF.

    response_model is intentionally omitted — the body is a binary .pdf file.

    Args:
        invoice_id: UUID of the invoice.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        Response: The .pdf export file.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    detail = await get_invoice_detail(db, effective_brand_id, invoice_id)
    _assert_site_visible(access, detail.site_id)
    # WeasyPrint rendering is CPU-bound and can take seconds — run it in a
    # worker thread so it never blocks the event loop (and with it, every
    # other in-flight request on this single-process server)
    pdf_bytes = await asyncio.to_thread(render_invoice_pdf, detail)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=invoice_{invoice_id}.pdf"},
    )


@router.post(
    "/{invoice_id}/refund",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def refund_invoice_report(
    invoice_id: uuid.UUID,
    payload: RefundRequest,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> InvoiceResponse:
    """
    Refund a paid invoice from the management portal — full, or partial by
    line item (see RefundRequest.line_item_ids).

    The transactional POST /invoices/{id}/refund in routes/invoices.py
    remains the POS terminal's own refund path (requires an open till
    session, attributes the refund to that shift); this route is the
    portal-initiated equivalent, so register_session_id is None — a
    portal-issued refund isn't tied to any till session.

    Args:
        invoice_id: UUID of the original paid invoice to refund.
        payload: Optional reason, and optionally line_item_ids for a partial refund.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (management or portal).
        db: Active database session.

    Returns:
        InvoiceResponse: The newly created refund invoice.

    Raises:
        HTTPException: 403 if the invoice's site is outside the caller's scope.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    site_id = await get_invoice_site_id(db, effective_brand_id, invoice_id)
    _assert_site_visible(access, site_id)
    refund = await create_refund(
        db, effective_brand_id, invoice_id, payload, access.actor_user, register_session_id=None
    )
    return InvoiceResponse.model_validate(refund)
