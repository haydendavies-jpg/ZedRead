"""Admin-only routes for managing jurisdiction-scoped tax templates.

Every route requires a portal-admin token (require_super_admin) —
management-portal (customer) users can never see or modify tax templates.
Routes stay thin: all logic lives in tax_template_service.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.tax_template import (
    TaxTemplateCreate,
    TaxTemplateRateCreate,
    TaxTemplateRateResponse,
    TaxTemplateRateUpdate,
    TaxTemplateResponse,
    TaxTemplateUpdate,
)
from app.services import tax_template_service
from app.utils.dependencies import require_super_admin

router = APIRouter(prefix="/admin/tax-templates", tags=["admin"])


@router.get("/", response_model=list[TaxTemplateResponse], status_code=status.HTTP_200_OK)
async def list_tax_templates(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    country: str | None = Query(None, min_length=2, max_length=2),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
) -> list[TaxTemplateResponse]:
    """List tax templates (with rates), optionally filtered by country."""
    return await tax_template_service.list_templates(db, skip=skip, limit=limit, country=country)


@router.post("/", response_model=TaxTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_tax_template(
    payload: TaxTemplateCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
) -> TaxTemplateResponse:
    """Create a tax template for a jurisdiction."""
    return await tax_template_service.create_template(db, payload, admin)


@router.patch("/{template_id}", response_model=TaxTemplateResponse, status_code=status.HTTP_200_OK)
async def update_tax_template(
    template_id: uuid.UUID,
    payload: TaxTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
) -> TaxTemplateResponse:
    """Update a tax template's name, jurisdiction fields, or active state."""
    return await tax_template_service.update_template(db, template_id, payload, admin)


@router.delete("/{template_id}", response_model=dict, status_code=status.HTTP_200_OK)
async def delete_tax_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
) -> dict:
    """Soft-delete a tax template so it stops matching sites immediately."""
    await tax_template_service.delete_template(db, template_id, admin)
    return {"status": "deleted"}


@router.post(
    "/{template_id}/rates",
    response_model=TaxTemplateRateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tax_template_rate(
    template_id: uuid.UUID,
    payload: TaxTemplateRateCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
) -> TaxTemplateRateResponse:
    """Add a rate line to a tax template."""
    return await tax_template_service.create_rate(db, template_id, payload, admin)


@router.patch(
    "/rates/{rate_id}",
    response_model=TaxTemplateRateResponse,
    status_code=status.HTTP_200_OK,
)
async def update_tax_template_rate(
    rate_id: uuid.UUID,
    payload: TaxTemplateRateUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
) -> TaxTemplateRateResponse:
    """Update a template rate's name, percentage, model, or ordering."""
    return await tax_template_service.update_rate(db, rate_id, payload, admin)


@router.delete("/rates/{rate_id}", response_model=dict, status_code=status.HTTP_200_OK)
async def delete_tax_template_rate(
    rate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
) -> dict:
    """Soft-delete a template rate so it stops applying immediately."""
    await tax_template_service.delete_rate(db, rate_id, admin)
    return {"status": "deleted"}
