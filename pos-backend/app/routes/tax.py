"""Tax category and tax rate routes — scoped to the authenticated user's brand."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.tax import (
    TaxCategoryCreate,
    TaxCategoryResponse,
    TaxCategoryUpdate,
    TaxRateCreate,
    TaxRateResponse,
    TaxRateUpdate,
)
from app.services import tax_service
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(prefix="/tax", tags=["tax"])


# ── Tax categories ────────────────────────────────────────────────────────────


@router.get(
    "/categories",
    response_model=list[TaxCategoryResponse],
    status_code=status.HTTP_200_OK,
)
async def list_tax_categories(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[TaxCategoryResponse]:
    """
    List active tax categories for the authenticated user's brand.

    Args:
        skip: Pagination offset.
        limit: Maximum number of categories to return.
        access: Resolved POS access (user, site, profile) from JWT.
        db: Active database session.

    Returns:
        list[TaxCategoryResponse]: Tax categories for the brand.
    """
    cats = await tax_service.list_tax_categories(db, access.effective_brand_id(brand_id), skip, limit)
    return [TaxCategoryResponse.model_validate(c) for c in cats]


@router.post(
    "/categories",
    response_model=TaxCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tax_category(
    payload: TaxCategoryCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> TaxCategoryResponse:
    """
    Create a new tax category for the authenticated user's brand.

    Args:
        payload: Tax category creation data.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        TaxCategoryResponse: The created category.
    """
    cat = await tax_service.create_tax_category(db, access.effective_brand_id(brand_id), payload, access.actor_user)
    return TaxCategoryResponse.model_validate(cat)


@router.patch(
    "/categories/{tax_category_id}",
    response_model=TaxCategoryResponse,
    status_code=status.HTTP_200_OK,
)
async def update_tax_category(
    tax_category_id: uuid.UUID,
    payload: TaxCategoryUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> TaxCategoryResponse:
    """
    Update a tax category's name.

    Args:
        tax_category_id: UUID of the category to update.
        payload: Fields to update.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        TaxCategoryResponse: The updated category.
    """
    cat = await tax_service.update_tax_category(
        db, access.effective_brand_id(brand_id), tax_category_id, payload, access.actor_user
    )
    return TaxCategoryResponse.model_validate(cat)


# ── Tax rates ─────────────────────────────────────────────────────────────────


@router.get(
    "/categories/{tax_category_id}/rates",
    response_model=list[TaxRateResponse],
    status_code=status.HTTP_200_OK,
)
async def list_tax_rates(
    tax_category_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[TaxRateResponse]:
    """
    List active tax rates for a tax category.

    Args:
        tax_category_id: UUID of the parent tax category.
        skip: Pagination offset.
        limit: Maximum number of rates to return.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        list[TaxRateResponse]: Active rates for the category.
    """
    rates = await tax_service.list_tax_rates(
        db, access.effective_brand_id(brand_id), tax_category_id, skip, limit
    )
    return [TaxRateResponse.model_validate(r) for r in rates]


@router.post(
    "/categories/{tax_category_id}/rates",
    response_model=TaxRateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tax_rate(
    tax_category_id: uuid.UUID,
    payload: TaxRateCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> TaxRateResponse:
    """
    Add a tax rate to a tax category.

    Args:
        tax_category_id: UUID of the parent tax category.
        payload: Rate data (name, rate_percent, tax_model).
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        TaxRateResponse: The created rate.
    """
    rate = await tax_service.create_tax_rate(
        db, access.effective_brand_id(brand_id), tax_category_id, payload, access.actor_user
    )
    return TaxRateResponse.model_validate(rate)


@router.patch(
    "/rates/{tax_rate_id}",
    response_model=TaxRateResponse,
    status_code=status.HTTP_200_OK,
)
async def update_tax_rate(
    tax_rate_id: uuid.UUID,
    payload: TaxRateUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> TaxRateResponse:
    """
    Update a tax rate's name, rate_percent, or tax_model.

    Args:
        tax_rate_id: UUID of the rate to update.
        payload: Fields to update.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        TaxRateResponse: The updated rate.
    """
    rate = await tax_service.update_tax_rate(
        db, access.effective_brand_id(brand_id), tax_rate_id, payload, access.actor_user
    )
    return TaxRateResponse.model_validate(rate)
