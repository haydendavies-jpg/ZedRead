"""Integration tests for the invoice engine — Stage 10.

15 test scenarios covering: invoice creation, line item snapshots, modifiers,
tax calculation, discounts, payment, void, refund, and error paths.

Written BEFORE any service code (TDD gate — Stage 10 plan rule).
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.invoice import Invoice
from app.models.invoice_line_item import InvoiceLineItem
from app.models.payment import Payment
from app.models.tax_category import TaxCategory
from app.models.tax_template import TaxTemplate
from app.models.tax_template_rate import TaxTemplateRate


# ── Fixtures ──────────────────────────────────────────────────────────────────


async def _seed_au_template(db: AsyncSession, tax_model: str) -> None:
    """Create an AU country-level tax template with a single 10% GST rate."""
    template = TaxTemplate(id=uuid.uuid4(), name="Australia GST", country="AU", is_active=True)
    db.add(template)
    await db.flush()
    db.add(
        TaxTemplateRate(
            id=uuid.uuid4(),
            tax_template_id=template.id,
            name="GST",
            rate_percent=Decimal("10.0000"),
            tax_model=tax_model,
            is_active=True,
        )
    )


@pytest_asyncio.fixture()
async def test_tax_cat_exclusive(db: AsyncSession, test_brand) -> TaxCategory:
    """A taxed (non-tax-free) category plus an AU template with a 10% exclusive rate.

    Rates now come from admin templates matched to the site's location, not the
    brand tax category — the category only marks the product as taxed vs tax-free.
    """
    tc = TaxCategory(id=uuid.uuid4(), brand_id=test_brand.id, name="Standard", is_active=True, is_system=True, is_tax_free=False)
    db.add(tc)
    await _seed_au_template(db, "exclusive")
    await db.commit()
    await db.refresh(tc)
    return tc


@pytest_asyncio.fixture()
async def test_tax_cat_inclusive(db: AsyncSession, test_brand) -> TaxCategory:
    """A taxed category plus an AU template with a 10% inclusive rate."""
    tc = TaxCategory(id=uuid.uuid4(), brand_id=test_brand.id, name="Standard", is_active=True, is_system=True, is_tax_free=False)
    db.add(tc)
    await _seed_au_template(db, "inclusive")
    await db.commit()
    await db.refresh(tc)
    return tc


# ── Helper: create an invoice via the API ─────────────────────────────────────


async def _create_invoice(client: AsyncClient, headers: dict) -> str:
    """POST /invoices and return the invoice ID."""
    resp = await client.post("/invoices", json={}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _add_line_item(
    client: AsyncClient,
    headers: dict,
    invoice_id: str,
    product_id: str,
    quantity: int = 1,
) -> dict:
    """POST /invoices/{id}/line-items and return the response JSON."""
    resp = await client.post(
        f"/invoices/{invoice_id}/line-items",
        json={"product_id": product_id, "quantity": quantity},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Test scenarios ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_invoice_returns_201_draft(
    client: AsyncClient,
    pos_auth_headers: dict,
) -> None:
    """POST /invoices creates a draft invoice scoped to the user's site."""
    resp = await client.post("/invoices", json={}, headers=pos_auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "draft"
    assert data["invoice_type"] == "sale"
    assert data["total_cents"] == 0


@pytest.mark.asyncio
async def test_create_invoice_writes_audit_log(
    client: AsyncClient,
    pos_auth_headers: dict,
    db: AsyncSession,
) -> None:
    """Creating an invoice writes an 'invoice.created' audit row."""
    await client.post("/invoices", json={}, headers=pos_auth_headers)
    result = await db.execute(select(AuditLog).where(AuditLog.action == "invoice.created"))
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_add_line_item_snapshots_product_data(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """Adding a line item copies product_name and unit_price_cents onto the row."""
    invoice_id = await _create_invoice(client, pos_auth_headers)

    resp = await client.post(
        f"/invoices/{invoice_id}/line-items",
        json={"product_id": str(test_product.id), "quantity": 1},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["product_name"] == test_product.name
    assert data["unit_price_cents"] == test_product.base_price_cents
    assert data["quantity"] == 1

    # Verify snapshot is persisted in DB
    row = await db.execute(select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == uuid.UUID(invoice_id)))
    line = row.scalar_one()
    assert line.product_name == test_product.name
    assert line.unit_price_cents == test_product.base_price_cents


@pytest.mark.asyncio
async def test_add_line_item_unknown_product_returns_404(
    client: AsyncClient,
    pos_auth_headers: dict,
) -> None:
    """Adding a non-existent product as a line item returns 404."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    resp = await client.post(
        f"/invoices/{invoice_id}/line-items",
        json={"product_id": str(uuid.uuid4()), "quantity": 1},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_add_line_item_calculates_exclusive_tax(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    test_brand,
    test_tax_cat_exclusive: TaxCategory,
    db: AsyncSession,
) -> None:
    """Line item with exclusive 10% tax: tax_cents and line_total_cents are correct."""
    from app.models.product import Product

    # Attach the tax category to the product
    product = await db.get(Product, test_product.id)
    product.tax_category_id = test_tax_cat_exclusive.id
    await db.commit()

    invoice_id = await _create_invoice(client, pos_auth_headers)
    resp = await client.post(
        f"/invoices/{invoice_id}/line-items",
        json={"product_id": str(test_product.id), "quantity": 2},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    # base_price = 1500 (from conftest test_product), qty=2, subtotal=3000
    # exclusive 10% tax = 300, line_total = 3300
    assert data["subtotal_cents"] == 3000
    assert data["tax_cents"] == 300
    assert data["line_total_cents"] == 3300


@pytest.mark.asyncio
async def test_add_line_item_tax_free_product_has_no_tax(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    test_brand,
    test_tax_cat_exclusive: TaxCategory,
    db: AsyncSession,
) -> None:
    """A product in a Tax Free category gets zero tax even when a template matches the site."""
    from app.models.product import Product
    from app.models.tax_category import TaxCategory as TC

    # test_tax_cat_exclusive also seeded the AU template; add a Tax Free category
    free = TC(id=uuid.uuid4(), brand_id=test_brand.id, name="Tax Free", is_active=True, is_system=True, is_tax_free=True)
    db.add(free)
    await db.flush()  # insert the category before the product FK references it
    product = await db.get(Product, test_product.id)
    product.tax_category_id = free.id
    await db.commit()

    invoice_id = await _create_invoice(client, pos_auth_headers)
    resp = await client.post(
        f"/invoices/{invoice_id}/line-items",
        json={"product_id": str(test_product.id), "quantity": 2},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["subtotal_cents"] == 3000
    assert data["tax_cents"] == 0
    assert data["line_total_cents"] == 3000


@pytest.mark.asyncio
async def test_add_line_item_with_modifier(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
) -> None:
    """Adding a modifier to a line item snapshots modifier_name and price_delta_cents."""
    invoice_id = await _create_invoice(client, pos_auth_headers)

    # Create a modifier group and option
    mg_resp = await client.post(
        "/modifier-groups",
        json={"name": "Extras", "min_selections": 0, "max_selections": 3},
        headers=pos_auth_headers,
    )
    group_id = mg_resp.json()["id"]

    opt_resp = await client.post(
        f"/modifier-groups/{group_id}/options",
        json={"name": "Extra Cheese", "price_delta_cents": 50},
        headers=pos_auth_headers,
    )
    option_id = opt_resp.json()["id"]

    line_resp = await client.post(
        f"/invoices/{invoice_id}/line-items",
        json={"product_id": str(test_product.id), "quantity": 1},
        headers=pos_auth_headers,
    )
    line_id = line_resp.json()["id"]

    mod_resp = await client.post(
        f"/invoices/{invoice_id}/line-items/{line_id}/modifiers",
        json={"modifier_option_id": option_id},
        headers=pos_auth_headers,
    )
    assert mod_resp.status_code == 201
    data = mod_resp.json()
    assert data["modifier_name"] == "Extra Cheese"
    assert data["price_delta_cents"] == 50


@pytest.mark.asyncio
async def test_apply_discount_to_invoice(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
) -> None:
    """POST /invoices/{id}/discount updates discount_cents and total_cents."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id))

    resp = await client.post(
        f"/invoices/{invoice_id}/discount",
        json={"discount_cents": 200, "reason": "Staff discount"},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["discount_cents"] == 200
    assert data["discount_reason"] == "Staff discount"
    # total should reflect the discount
    assert data["total_cents"] == data["subtotal_cents"] + data["tax_cents"] - 200


@pytest.mark.asyncio
async def test_apply_discount_writes_audit_log(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """Applying a discount writes an 'invoice.discount.applied' audit row."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id))
    await client.post(
        f"/invoices/{invoice_id}/discount",
        json={"discount_cents": 100, "reason": "Loyalty"},
        headers=pos_auth_headers,
    )
    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "invoice.discount.applied")
    )
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_pay_invoice_creates_payment_and_marks_paid(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """POST /invoices/{id}/pay creates a Payment row and sets status=paid."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id))

    resp = await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "cash", "amount_cents": 1500},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "paid"
    assert data["paid_at"] is not None

    # Verify Payment row created
    pay_result = await db.execute(
        select(Payment).where(Payment.invoice_id == uuid.UUID(invoice_id))
    )
    payment = pay_result.scalar_one_or_none()
    assert payment is not None
    assert payment.amount_cents == 1500
    assert payment.method == "cash"


@pytest.mark.asyncio
async def test_pay_invoice_writes_audit_log(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """Paying an invoice writes an 'invoice.paid' audit row."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id))
    await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "cash", "amount_cents": 1500},
        headers=pos_auth_headers,
    )
    result = await db.execute(select(AuditLog).where(AuditLog.action == "invoice.paid"))
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_pay_already_paid_invoice_returns_409(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
) -> None:
    """Paying an already-paid invoice returns 409 Conflict."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id))

    payload = {"method": "cash", "amount_cents": 1500}
    r1 = await client.post(f"/invoices/{invoice_id}/pay", json=payload, headers=pos_auth_headers)
    assert r1.status_code == 200

    r2 = await client.post(f"/invoices/{invoice_id}/pay", json=payload, headers=pos_auth_headers)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_void_invoice_sets_status_voided(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
) -> None:
    """POST /invoices/{id}/void sets status=voided and voided_at timestamp."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id))

    resp = await client.post(f"/invoices/{invoice_id}/void", headers=pos_auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "voided"
    assert data["voided_at"] is not None


@pytest.mark.asyncio
async def test_void_already_voided_invoice_returns_409(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
) -> None:
    """Voiding an already-voided invoice returns 409 Conflict."""
    invoice_id = await _create_invoice(client, pos_auth_headers)

    r1 = await client.post(f"/invoices/{invoice_id}/void", headers=pos_auth_headers)
    assert r1.status_code == 200

    r2 = await client.post(f"/invoices/{invoice_id}/void", headers=pos_auth_headers)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_refund_invoice_creates_refund_invoice(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """POST /invoices/{id}/refund creates a refund invoice linked to the original."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id))
    await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "cash", "amount_cents": 1500},
        headers=pos_auth_headers,
    )

    resp = await client.post(
        f"/invoices/{invoice_id}/refund",
        json={"reason": "Customer unhappy"},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["invoice_type"] == "refund"
    assert data["refund_of_id"] == invoice_id
    assert data["status"] == "paid"

    # Original invoice should be marked as refunded
    orig = await db.get(Invoice, uuid.UUID(invoice_id))
    assert orig is not None
    assert orig.is_refunded is True


@pytest.mark.asyncio
async def test_list_invoices_returns_site_invoices(
    client: AsyncClient,
    pos_auth_headers: dict,
) -> None:
    """GET /invoices returns invoices for the authenticated user's site."""
    # Create two invoices
    await client.post("/invoices", json={}, headers=pos_auth_headers)
    await client.post("/invoices", json={}, headers=pos_auth_headers)

    resp = await client.get("/invoices", headers=pos_auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
