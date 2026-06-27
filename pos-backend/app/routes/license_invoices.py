"""Routes for license invoice management (portal authenticated)."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.superadmin import SuperAdmin
from app.schemas.license_invoice import (
    LicenseInvoiceCreate,
    LicenseInvoicePayRequest,
    LicenseInvoiceResponse,
)
from app.services import license_invoice_service
from app.utils.dependencies import get_current_superadmin

router = APIRouter(prefix="/license-invoices", tags=["license-invoices"])


@router.get("/", response_model=list[LicenseInvoiceResponse])
async def list_invoices(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: SuperAdmin = Depends(get_current_superadmin),
) -> list[LicenseInvoiceResponse]:
    """List all license invoices with pagination."""
    return await license_invoice_service.list_invoices(db, skip=skip, limit=limit)


@router.get("/{invoice_id}", response_model=LicenseInvoiceResponse)
async def get_invoice(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: SuperAdmin = Depends(get_current_superadmin),
) -> LicenseInvoiceResponse:
    """Fetch a single license invoice by ID."""
    return await license_invoice_service.get_invoice(db, invoice_id)


@router.post("/", response_model=LicenseInvoiceResponse, status_code=201)
async def create_invoice(
    payload: LicenseInvoiceCreate,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> LicenseInvoiceResponse:
    """Raise a new invoice against a license."""
    return await license_invoice_service.create_invoice(db, payload, actor)


@router.post("/{invoice_id}/pay", response_model=LicenseInvoiceResponse)
async def pay_invoice(
    invoice_id: uuid.UUID,
    payload: LicenseInvoicePayRequest,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> LicenseInvoiceResponse:
    """Mark an open invoice as paid."""
    return await license_invoice_service.pay_invoice(db, invoice_id, payload, actor)
