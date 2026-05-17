"""Integration tests for reporting routes.

Five scenarios: scope enforcement (403 for wrong site), happy paths for each
report endpoint, and data presence after creating paid invoices.
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tax_category import TaxCategory
from app.models.tax_rate import TaxRate


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _create_paid_invoice(
    client: AsyncClient, headers: dict, product_id: str, amount_cents: int
) -> None:
    """Helper: create invoice, add line item, and pay it."""
    inv_resp = await client.post("/invoices", json={}, headers=headers)
    assert inv_resp.status_code == 201
    invoice_id = inv_resp.json()["id"]

    li_resp = await client.post(
        f"/invoices/{invoice_id}/line-items",
        json={"product_id": product_id, "quantity": 1},
        headers=headers,
    )
    assert li_resp.status_code == 201

    pay_resp = await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "cash", "amount_cents": amount_cents},
        headers=headers,
    )
    assert pay_resp.status_code == 200


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_daily_sales_wrong_site_returns_403(
    client: AsyncClient,
    pos_auth_headers: dict,
) -> None:
    """Requesting daily sales for a different site_id returns 403."""
    wrong_site_id = str(uuid.uuid4())
    resp = await client.get(
        f"/reports/daily-sales?site_id={wrong_site_id}",
        headers=pos_auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_product_revenue_wrong_site_returns_403(
    client: AsyncClient,
    pos_auth_headers: dict,
) -> None:
    """Requesting product revenue for a different site_id returns 403."""
    wrong_site_id = str(uuid.uuid4())
    resp = await client.get(
        f"/reports/product-revenue?site_id={wrong_site_id}",
        headers=pos_auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_daily_sales_returns_data_for_paid_invoices(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    test_site,
) -> None:
    """After creating a paid invoice, daily-sales report returns a row."""
    await _create_paid_invoice(
        client, pos_auth_headers, str(test_product.id), test_product.base_price_cents
    )

    resp = await client.get(
        f"/reports/daily-sales?site_id={test_site.id}",
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 1
    assert rows[0]["invoice_count"] >= 1
    assert rows[0]["total_cents"] > 0


@pytest.mark.asyncio
async def test_product_revenue_returns_correct_product(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    test_site,
) -> None:
    """After a paid invoice, product-revenue report includes the product."""
    await _create_paid_invoice(
        client, pos_auth_headers, str(test_product.id), test_product.base_price_cents
    )

    resp = await client.get(
        f"/reports/product-revenue?site_id={test_site.id}",
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 1
    names = [r["product_name"] for r in rows]
    assert test_product.name in names


@pytest.mark.asyncio
async def test_payment_methods_returns_cash_after_payment(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    test_site,
) -> None:
    """After a cash payment, payment-methods report shows the cash entry."""
    await _create_paid_invoice(
        client, pos_auth_headers, str(test_product.id), test_product.base_price_cents
    )

    resp = await client.get(
        f"/reports/payment-methods?site_id={test_site.id}",
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200
    rows = resp.json()
    methods = [r["method"] for r in rows]
    assert "cash" in methods


@pytest.mark.asyncio
async def test_tax_collected_returns_empty_with_no_tax(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_site,
) -> None:
    """Tax-collected returns an empty list when no tax rates have been applied."""
    resp = await client.get(
        f"/reports/tax-collected?site_id={test_site.id}",
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []
