"""Business logic for reporting queries.

All report functions enforce brand/site scope — callers must supply their own
brand_id and site_id (resolved from the POS access token).  Attempting to
query data for a different brand raises HTTP 403.

Reports read from the 8 views created in migration 0010.  They never write
to the database and never call log_action().
"""

import uuid
from datetime import date

import structlog
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


# ── Inline Pydantic schemas ───────────────────────────────────────────────────

from decimal import Decimal

from pydantic import BaseModel


class DailySalesRow(BaseModel):
    """One row from vw_daily_sales."""

    sale_date: date
    invoice_count: int
    subtotal_cents: int
    tax_cents: int
    discount_cents: int
    total_cents: int


class ProductRevenueRow(BaseModel):
    """One row from vw_product_revenue."""

    product_id: uuid.UUID | None
    product_name: str
    total_units: int
    revenue_cents: int
    tax_cents: int


class PaymentMethodRow(BaseModel):
    """One row from vw_payment_methods."""

    method: str
    payment_count: int
    total_amount_cents: int


class TaxCollectedRow(BaseModel):
    """One row from vw_tax_collected."""

    tax_rate_name: str
    rate_percent: Decimal
    tax_model: str
    taxable_amount_cents: int
    tax_amount_cents: int


# ── Helpers ───────────────────────────────────────────────────────────────────


def _assert_brand_scope(requested_brand_id: uuid.UUID, user_brand_id: uuid.UUID) -> None:
    """
    Raise HTTP 403 if the requested brand does not match the authenticated user's brand.

    Args:
        requested_brand_id: The brand_id from the query parameter.
        user_brand_id: The brand_id resolved from the POS access token.

    Raises:
        HTTPException: 403 if brands do not match.
    """
    if requested_brand_id != user_brand_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: report scope exceeds your brand",
        )


def _assert_site_scope(
    requested_site_id: uuid.UUID, user_site_id: uuid.UUID
) -> None:
    """
    Raise HTTP 403 if the requested site does not match the authenticated user's site.

    Args:
        requested_site_id: The site_id from the query parameter.
        user_site_id: The site_id resolved from the POS access token.

    Raises:
        HTTPException: 403 if sites do not match.
    """
    if requested_site_id != user_site_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: report scope exceeds your site",
        )


# ── Report functions ──────────────────────────────────────────────────────────


async def get_daily_sales(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[DailySalesRow]:
    """
    Return daily sales totals for a site from vw_daily_sales.

    Args:
        db: Active database session.
        brand_id: Brand scope (already validated by caller).
        site_id: Site scope (already validated by caller).
        start_date: Optional lower bound (inclusive).
        end_date: Optional upper bound (inclusive).

    Returns:
        list[DailySalesRow]: Daily totals ordered by sale_date ascending.
    """
    sql = """
        SELECT sale_date, invoice_count, subtotal_cents, tax_cents,
               discount_cents, total_cents
        FROM vw_daily_sales
        WHERE brand_id = :brand_id AND site_id = :site_id
    """
    params: dict = {"brand_id": brand_id, "site_id": site_id}

    if start_date is not None:
        sql += " AND sale_date >= :start_date"
        params["start_date"] = start_date
    if end_date is not None:
        sql += " AND sale_date <= :end_date"
        params["end_date"] = end_date

    sql += " ORDER BY sale_date ASC"

    result = await db.execute(text(sql), params)
    rows = result.mappings().all()
    return [DailySalesRow(**dict(row)) for row in rows]


async def get_product_revenue(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID,
    limit: int = 50,
) -> list[ProductRevenueRow]:
    """
    Return product revenue totals for a site from vw_product_revenue.

    Args:
        db: Active database session.
        brand_id: Brand scope (already validated by caller).
        site_id: Site scope (already validated by caller).
        limit: Maximum rows to return.

    Returns:
        list[ProductRevenueRow]: Products ordered by revenue descending.
    """
    result = await db.execute(
        text(
            """
            SELECT product_id, product_name, total_units, revenue_cents, tax_cents
            FROM vw_product_revenue
            WHERE brand_id = :brand_id AND site_id = :site_id
            ORDER BY revenue_cents DESC
            LIMIT :limit
            """
        ),
        {"brand_id": brand_id, "site_id": site_id, "limit": limit},
    )
    rows = result.mappings().all()
    return [ProductRevenueRow(**dict(row)) for row in rows]


async def get_payment_methods(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID,
) -> list[PaymentMethodRow]:
    """
    Return payment method breakdown for a site from vw_payment_methods.

    Args:
        db: Active database session.
        brand_id: Brand scope (already validated by caller).
        site_id: Site scope (already validated by caller).

    Returns:
        list[PaymentMethodRow]: Payment totals by method.
    """
    result = await db.execute(
        text(
            """
            SELECT method, payment_count, total_amount_cents
            FROM vw_payment_methods
            WHERE brand_id = :brand_id AND site_id = :site_id
            ORDER BY total_amount_cents DESC
            """
        ),
        {"brand_id": brand_id, "site_id": site_id},
    )
    rows = result.mappings().all()
    return [PaymentMethodRow(**dict(row)) for row in rows]


async def get_tax_collected(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID,
) -> list[TaxCollectedRow]:
    """
    Return tax collected by rate for a site from vw_tax_collected.

    Args:
        db: Active database session.
        brand_id: Brand scope (already validated by caller).
        site_id: Site scope (already validated by caller).

    Returns:
        list[TaxCollectedRow]: Tax totals by rate name.
    """
    result = await db.execute(
        text(
            """
            SELECT tax_rate_name, rate_percent, tax_model,
                   taxable_amount_cents, tax_amount_cents
            FROM vw_tax_collected
            WHERE brand_id = :brand_id AND site_id = :site_id
            ORDER BY tax_amount_cents DESC
            """
        ),
        {"brand_id": brand_id, "site_id": site_id},
    )
    rows = result.mappings().all()
    return [TaxCollectedRow(**dict(row)) for row in rows]
