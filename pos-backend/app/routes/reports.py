"""Reporting routes — brand/site scoped read-only analytics."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.report_service import (
    DailySalesRow,
    PaymentMethodRow,
    ProductRevenueRow,
    TaxCollectedRow,
    _assert_brand_scope,
    _assert_site_scope,
    get_daily_sales,
    get_payment_methods,
    get_product_revenue,
    get_tax_collected,
)
from app.utils.dependencies import POSAccess, resolve_access

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get(
    "/daily-sales",
    response_model=list[DailySalesRow],
    status_code=status.HTTP_200_OK,
)
async def daily_sales_report(
    site_id: uuid.UUID = Query(..., description="Must match the authenticated user's site"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> list[DailySalesRow]:
    """
    Daily sales totals for a site.

    Args:
        site_id: Site to report on — must match the authenticated user's site.
        start_date: Optional start of date range (inclusive).
        end_date: Optional end of date range (inclusive).
        access: Resolved POS access.
        db: Active database session.

    Returns:
        list[DailySalesRow]: Daily totals ordered by date ascending.

    Raises:
        HTTPException: 403 if site_id does not match the user's site.
    """
    _assert_site_scope(site_id, access.site.id)
    return await get_daily_sales(db, access.user.brand_id, site_id, start_date, end_date)


@router.get(
    "/product-revenue",
    response_model=list[ProductRevenueRow],
    status_code=status.HTTP_200_OK,
)
async def product_revenue_report(
    site_id: uuid.UUID = Query(..., description="Must match the authenticated user's site"),
    limit: int = Query(50, ge=1, le=200),
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> list[ProductRevenueRow]:
    """
    Product revenue totals ordered by revenue descending.

    Args:
        site_id: Site to report on.
        limit: Maximum products to return.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        list[ProductRevenueRow]: Products with total units and revenue.

    Raises:
        HTTPException: 403 if site_id does not match the user's site.
    """
    _assert_site_scope(site_id, access.site.id)
    return await get_product_revenue(db, access.user.brand_id, site_id, limit)


@router.get(
    "/payment-methods",
    response_model=list[PaymentMethodRow],
    status_code=status.HTTP_200_OK,
)
async def payment_methods_report(
    site_id: uuid.UUID = Query(..., description="Must match the authenticated user's site"),
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> list[PaymentMethodRow]:
    """
    Payment method breakdown (cash vs card vs voucher).

    Args:
        site_id: Site to report on.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        list[PaymentMethodRow]: Totals by payment method.

    Raises:
        HTTPException: 403 if site_id does not match the user's site.
    """
    _assert_site_scope(site_id, access.site.id)
    return await get_payment_methods(db, access.user.brand_id, site_id)


@router.get(
    "/tax-collected",
    response_model=list[TaxCollectedRow],
    status_code=status.HTTP_200_OK,
)
async def tax_collected_report(
    site_id: uuid.UUID = Query(..., description="Must match the authenticated user's site"),
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> list[TaxCollectedRow]:
    """
    Tax collected by rate name for a site.

    Args:
        site_id: Site to report on.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        list[TaxCollectedRow]: Tax amounts by rate.

    Raises:
        HTTPException: 403 if site_id does not match the user's site.
    """
    _assert_site_scope(site_id, access.site.id)
    return await get_tax_collected(db, access.user.brand_id, site_id)
