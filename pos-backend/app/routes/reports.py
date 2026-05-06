"""Reporting routes — brand/site scoped read-only analytics."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.report_service import (
    DailySalesRow,
    PaymentMethodRow,
    ProductRevenueRow,
    TaxCollectedRow,
    _assert_site_scope,
    get_daily_sales,
    get_payment_methods,
    get_product_revenue,
    get_tax_collected,
)
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(prefix="/reports", tags=["reports"])


def _check_site_access(access: CatalogAccess, site_id: uuid.UUID) -> None:
    """
    Validate that the caller has access to the requested site_id.

    POS terminal users and site-scope management users are restricted to their
    own site. Brand-scope and group-scope management users, and portal admin
    users, may request any site_id within their authority (the service layer
    handles the brand/group boundary check).

    Args:
        access: The resolved catalog access context.
        site_id: The site_id from the query parameter.

    Raises:
        HTTPException: 403 if a POS or site-scope management user requests a site
                       that does not match their token.
    """
    if access.pos_access:
        _assert_site_scope(site_id, access.pos_access.site.id)
        return
    if access.mgmt_access and access.mgmt_access.scope == "site" and access.mgmt_access.site:
        _assert_site_scope(site_id, access.mgmt_access.site.id)
        return
    # Brand-scope, group-scope, or portal admin: no single-site restriction


@router.get(
    "/daily-sales",
    response_model=list[DailySalesRow],
    status_code=status.HTTP_200_OK,
)
async def daily_sales_report(
    site_id: uuid.UUID = Query(..., description="Site to report on"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[DailySalesRow]:
    """
    Daily sales totals for a site.

    POS terminal and site-scope management users are restricted to their own
    site. Brand-scope, group-scope, and portal admin users may supply any
    site_id within their authority.

    Args:
        site_id: Site to report on.
        start_date: Optional start of date range (inclusive).
        end_date: Optional end of date range (inclusive).
        brand_id: Override brand_id for group/portal access.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        list[DailySalesRow]: Daily totals ordered by date ascending.
    """
    _check_site_access(access, site_id)
    try:
        effective_brand_id = brand_id if brand_id and access.portal_access else access.brand_id
    except ValueError:
        if not brand_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="brand_id query parameter required for group or portal admin access",
            )
        effective_brand_id = brand_id
    return await get_daily_sales(db, effective_brand_id, site_id, start_date, end_date)


@router.get(
    "/product-revenue",
    response_model=list[ProductRevenueRow],
    status_code=status.HTTP_200_OK,
)
async def product_revenue_report(
    site_id: uuid.UUID = Query(..., description="Site to report on"),
    limit: int = Query(50, ge=1, le=200),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[ProductRevenueRow]:
    """
    Product revenue totals ordered by revenue descending.

    Args:
        site_id: Site to report on.
        limit: Maximum products to return.
        brand_id: Override brand_id for group/portal access.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        list[ProductRevenueRow]: Products with total units and revenue.
    """
    _check_site_access(access, site_id)
    try:
        effective_brand_id = brand_id if brand_id and access.portal_access else access.brand_id
    except ValueError:
        if not brand_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="brand_id query parameter required for group or portal admin access",
            )
        effective_brand_id = brand_id
    return await get_product_revenue(db, effective_brand_id, site_id, limit)


@router.get(
    "/payment-methods",
    response_model=list[PaymentMethodRow],
    status_code=status.HTTP_200_OK,
)
async def payment_methods_report(
    site_id: uuid.UUID = Query(..., description="Site to report on"),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[PaymentMethodRow]:
    """
    Payment method breakdown (cash vs card vs voucher).

    Args:
        site_id: Site to report on.
        brand_id: Override brand_id for group/portal access.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        list[PaymentMethodRow]: Totals by payment method.
    """
    _check_site_access(access, site_id)
    try:
        effective_brand_id = brand_id if brand_id and access.portal_access else access.brand_id
    except ValueError:
        if not brand_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="brand_id query parameter required for group or portal admin access",
            )
        effective_brand_id = brand_id
    return await get_payment_methods(db, effective_brand_id, site_id)


@router.get(
    "/tax-collected",
    response_model=list[TaxCollectedRow],
    status_code=status.HTTP_200_OK,
)
async def tax_collected_report(
    site_id: uuid.UUID = Query(..., description="Site to report on"),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[TaxCollectedRow]:
    """
    Tax collected by rate name for a site.

    Args:
        site_id: Site to report on.
        brand_id: Override brand_id for group/portal access.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        list[TaxCollectedRow]: Tax amounts by rate.
    """
    _check_site_access(access, site_id)
    try:
        effective_brand_id = brand_id if brand_id and access.portal_access else access.brand_id
    except ValueError:
        if not brand_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="brand_id query parameter required for group or portal admin access",
            )
        effective_brand_id = brand_id
    return await get_tax_collected(db, effective_brand_id, site_id)
