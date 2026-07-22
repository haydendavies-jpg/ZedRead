"""Integration tests for the invoice engine — Stage 10.

15 test scenarios covering: invoice creation, line item snapshots, modifiers,
tax calculation, discounts, payment, void, refund, and error paths.

Written BEFORE any service code (TDD gate — Stage 10 plan rule).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.invoice import Invoice
from app.models.invoice_line_item import InvoiceLineItem
from app.models.payment import Payment


# ── Fixtures ──────────────────────────────────────────────────────────────────


async def _set_product_prices(
    db: AsyncSession, product_id, *, inc_cents: int, ex_cents: int, is_taxable: bool
) -> None:
    """Set a product's stored inclusive/exclusive prices and taxability directly.

    Tax is no longer computed from rates at sale time — the invoice engine reads
    these precomputed prices, so tests seed them on the product rather than
    creating tax categories/rates.
    """
    from app.models.product import Product

    product = await db.get(Product, product_id)
    product.base_price_cents = inc_cents
    product.price_ex_cents = ex_cents
    product.is_taxable = is_taxable
    await db.commit()


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
    assert data["ref"].startswith("INV-")


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
async def test_add_line_item_taxable_charges_inclusive_price(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """A taxable product is charged its inclusive price; tax = (inc − ex) per unit."""
    # inc 1100, ex 1000 → embedded GST of 100/unit
    await _set_product_prices(db, test_product.id, inc_cents=1100, ex_cents=1000, is_taxable=True)

    invoice_id = await _create_invoice(client, pos_auth_headers)
    resp = await client.post(
        f"/invoices/{invoice_id}/line-items",
        json={"product_id": str(test_product.id), "quantity": 2},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    # qty 2 → subtotal 2200 (inclusive), tax = (1100-1000)*2 = 200, total embedded
    assert data["subtotal_cents"] == 2200
    assert data["tax_cents"] == 200
    assert data["line_total_cents"] == 2200


@pytest.mark.asyncio
async def test_add_line_item_tax_free_product_charges_exclusive_price(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """A non-taxable product is charged its exclusive price with zero tax."""
    await _set_product_prices(db, test_product.id, inc_cents=1100, ex_cents=1000, is_taxable=False)

    invoice_id = await _create_invoice(client, pos_auth_headers)
    resp = await client.post(
        f"/invoices/{invoice_id}/line-items",
        json={"product_id": str(test_product.id), "quantity": 2},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    # qty 2 → charged at ex price 1000 → subtotal 2000, no tax
    assert data["subtotal_cents"] == 2000
    assert data["tax_cents"] == 0
    assert data["line_total_cents"] == 2000


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
async def test_add_line_item_modifier_writes_audit_log(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """Attaching a modifier writes an 'invoice.line_item.modifier_added' audit row."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
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
    line = await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id))

    resp = await client.post(
        f"/invoices/{invoice_id}/line-items/{line['id']}/modifiers",
        json={"modifier_option_id": option_id},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 201

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == line["id"],
            AuditLog.action == "invoice.line_item.modifier_added",
        )
    )
    row = result.scalar_one()
    assert row.after_state["modifier_option_id"] == option_id
    assert row.after_state["price_delta_cents"] == 50


@pytest.mark.asyncio
async def test_get_line_item_returns_attached_modifiers(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
) -> None:
    """GET /invoices/{id}/line-items/{id} returns the line plus its attached modifiers."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    mg_resp = await client.post(
        "/modifier-groups",
        json={"name": "Size", "min_selections": 1, "max_selections": 1},
        headers=pos_auth_headers,
    )
    group_id = mg_resp.json()["id"]
    opt_resp = await client.post(
        f"/modifier-groups/{group_id}/options",
        json={"name": "Large", "price_delta_cents": 60},
        headers=pos_auth_headers,
    )
    option_id = opt_resp.json()["id"]
    line = await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id))

    await client.post(
        f"/invoices/{invoice_id}/line-items/{line['id']}/modifiers",
        json={"modifier_option_id": option_id},
        headers=pos_auth_headers,
    )

    resp = await client.get(
        f"/invoices/{invoice_id}/line-items/{line['id']}", headers=pos_auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == line["id"]
    assert len(data["modifiers"]) == 1
    assert data["modifiers"][0]["modifier_name"] == "Large"
    assert data["modifiers"][0]["price_delta_cents"] == 60


@pytest.mark.asyncio
async def test_get_line_item_unknown_line_returns_404(
    client: AsyncClient,
    pos_auth_headers: dict,
) -> None:
    """GET /invoices/{id}/line-items/{id} for a non-existent line item returns 404."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    resp = await client.get(
        f"/invoices/{invoice_id}/line-items/{uuid.uuid4()}", headers=pos_auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_line_item_quantity_rescales_subtotal_and_tax(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """PATCH a line item's quantity rescales subtotal/tax/line_total from the snapshotted unit price."""
    # inc 1100, ex 1000 → embedded GST of 100/unit
    await _set_product_prices(db, test_product.id, inc_cents=1100, ex_cents=1000, is_taxable=True)
    invoice_id = await _create_invoice(client, pos_auth_headers)
    line = await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id), quantity=1)

    resp = await client.patch(
        f"/invoices/{invoice_id}/line-items/{line['id']}",
        json={"quantity": 3},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["quantity"] == 3
    assert data["subtotal_cents"] == 3300
    assert data["tax_cents"] == 300
    assert data["line_total_cents"] == 3300

    invoice_resp = await client.get(f"/invoices/{invoice_id}", headers=pos_auth_headers)
    assert invoice_resp.json()["total_cents"] == 3300


@pytest.mark.asyncio
async def test_update_line_item_quantity_writes_audit_log(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """Changing a line item's quantity writes an 'invoice.line_item.quantity_updated' audit row."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    line = await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id), quantity=1)

    await client.patch(
        f"/invoices/{invoice_id}/line-items/{line['id']}",
        json={"quantity": 2},
        headers=pos_auth_headers,
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == line["id"],
            AuditLog.action == "invoice.line_item.quantity_updated",
        )
    )
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_update_line_item_quantity_unknown_line_returns_404(
    client: AsyncClient,
    pos_auth_headers: dict,
) -> None:
    """PATCHing a non-existent line item returns 404."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    resp = await client.patch(
        f"/invoices/{invoice_id}/line-items/{uuid.uuid4()}",
        json={"quantity": 2},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_line_item_quantity_on_paid_invoice_returns_409(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
) -> None:
    """A paid invoice's line items can no longer be edited."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    line = await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id), quantity=1)
    invoice_resp = await client.get(f"/invoices/{invoice_id}", headers=pos_auth_headers)
    total = invoice_resp.json()["total_cents"]
    await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "cash", "amount_cents": total},
        headers=pos_auth_headers,
    )

    resp = await client.patch(
        f"/invoices/{invoice_id}/line-items/{line['id']}",
        json={"quantity": 2},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_remove_line_item_recomputes_invoice_totals(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """DELETEing a line item drops it from the invoice and recomputes totals."""
    await _set_product_prices(db, test_product.id, inc_cents=1100, ex_cents=1000, is_taxable=True)
    invoice_id = await _create_invoice(client, pos_auth_headers)
    line_a = await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id), quantity=1)
    line_b = await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id), quantity=1)

    resp = await client.delete(
        f"/invoices/{invoice_id}/line-items/{line_a['id']}",
        headers=pos_auth_headers,
    )
    assert resp.status_code == 204

    row = await db.execute(select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == uuid.UUID(invoice_id)))
    remaining = row.scalars().all()
    assert [str(item.id) for item in remaining] == [line_b["id"]]

    invoice_resp = await client.get(f"/invoices/{invoice_id}", headers=pos_auth_headers)
    assert invoice_resp.json()["total_cents"] == 1100


@pytest.mark.asyncio
async def test_remove_line_item_writes_audit_log(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """Removing a line item writes an 'invoice.line_item.removed' audit row."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    line = await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id), quantity=1)

    await client.delete(f"/invoices/{invoice_id}/line-items/{line['id']}", headers=pos_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == line["id"],
            AuditLog.action == "invoice.line_item.removed",
        )
    )
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_remove_line_item_on_paid_invoice_returns_409(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
) -> None:
    """A paid invoice's line items can no longer be removed."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    line = await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id), quantity=1)
    invoice_resp = await client.get(f"/invoices/{invoice_id}", headers=pos_auth_headers)
    total = invoice_resp.json()["total_cents"]
    await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "cash", "amount_cents": total},
        headers=pos_auth_headers,
    )

    resp = await client.delete(
        f"/invoices/{invoice_id}/line-items/{line['id']}",
        headers=pos_auth_headers,
    )
    assert resp.status_code == 409


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
async def test_pay_invoice_partial_amount_leaves_invoice_open(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """A split-payment leg smaller than the total records the payment but does not mark the invoice paid."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id))  # total 1500

    resp = await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "card", "amount_cents": 500},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "open"
    assert data["paid_at"] is None

    pay_result = await db.execute(select(Payment).where(Payment.invoice_id == uuid.UUID(invoice_id)))
    payments = pay_result.scalars().all()
    assert len(payments) == 1
    assert payments[0].amount_cents == 500


@pytest.mark.asyncio
async def test_pay_invoice_second_leg_completes_split_payment(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """A second payment leg covering the remaining balance marks the invoice paid."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id))  # total 1500

    first = await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "card", "amount_cents": 500},
        headers=pos_auth_headers,
    )
    assert first.json()["status"] == "open"

    second = await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "cash", "amount_cents": 1000},
        headers=pos_auth_headers,
    )
    assert second.status_code == 200
    data = second.json()
    assert data["status"] == "paid"
    assert data["paid_at"] is not None

    pay_result = await db.execute(select(Payment).where(Payment.invoice_id == uuid.UUID(invoice_id)))
    payments = pay_result.scalars().all()
    assert len(payments) == 2
    assert sum(p.amount_cents for p in payments) == 1500


@pytest.mark.asyncio
async def test_pay_invoice_partial_writes_payment_recorded_audit_log(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """A split-payment leg that doesn't cover the total writes 'invoice.payment.recorded', not 'invoice.paid'."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id))

    await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "card", "amount_cents": 500},
        headers=pos_auth_headers,
    )

    recorded = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == invoice_id, AuditLog.action == "invoice.payment.recorded"
        )
    )
    assert recorded.scalar_one_or_none() is not None

    paid = await db.execute(
        select(AuditLog).where(AuditLog.entity_id == invoice_id, AuditLog.action == "invoice.paid")
    )
    assert paid.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_pay_invoice_full_amount_still_writes_invoice_paid_audit_log(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """A single payment covering the full total still writes 'invoice.paid' (not the split-leg action)."""
    invoice_id = await _create_invoice(client, pos_auth_headers)
    await _add_line_item(client, pos_auth_headers, invoice_id, str(test_product.id))

    await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "cash", "amount_cents": 1500},
        headers=pos_auth_headers,
    )

    result = await db.execute(
        select(AuditLog).where(AuditLog.entity_id == invoice_id, AuditLog.action == "invoice.paid")
    )
    assert result.scalar_one_or_none() is not None


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
