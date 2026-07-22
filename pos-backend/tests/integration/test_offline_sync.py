"""Integration tests for offline-sync idempotency and checksum verification
(Android POS Phase 2) — client_ref dedup and SHA-256 checksums on invoices,
payments, and register sessions.

Covers:
1. Happy path — client_ref dedupes a retried write; a correct checksum is
   accepted and echoed back
2. Business rule violation — a checksum mismatch is rejected with 422
3. Audit log — a deduped retry does not write a second audit row
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.constants.audit_actions import INVOICE_CREATED, INVOICE_PAID, REGISTER_SESSION_OPENED
from app.models.audit_log import AuditLog
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.register_session import RegisterSession
from app.utils.checksum import sha256_hex

pytestmark = pytest.mark.asyncio


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ── Invoice creation idempotency ─────────────────────────────────────────────


async def test_create_invoice_client_ref_dedupes_retry(client, db, pos_auth_headers):
    """A retried create with the same client_ref returns the original invoice, no duplicate row."""
    client_ref = str(uuid.uuid4())

    first = await client.post("/invoices", json={"client_ref": client_ref}, headers=pos_auth_headers)
    second = await client.post("/invoices", json={"client_ref": client_ref}, headers=pos_auth_headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    count = (
        await db.execute(select(Invoice).where(Invoice.client_ref == client_ref))
    ).scalars().all()
    assert len(count) == 1


async def test_create_invoice_client_ref_dedupe_writes_one_audit_row(client, db, pos_auth_headers):
    """A deduped retry does not write a second INVOICE_CREATED audit row."""
    client_ref = str(uuid.uuid4())

    await client.post("/invoices", json={"client_ref": client_ref}, headers=pos_auth_headers)
    resp = await client.post("/invoices", json={"client_ref": client_ref}, headers=pos_auth_headers)
    invoice_id = resp.json()["id"]

    rows = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.entity_id == invoice_id, AuditLog.action == INVOICE_CREATED
            )
        )
    ).scalars().all()
    assert len(rows) == 1


async def test_create_invoice_without_client_ref_still_works(client, pos_auth_headers):
    """Omitting client_ref (existing callers) still creates a normal invoice."""
    response = await client.post("/invoices", json={}, headers=pos_auth_headers)
    assert response.status_code == 201
    assert response.json()["client_ref"] is None


# ── Payment idempotency + checksum ───────────────────────────────────────────


async def _open_invoice_with_line(client, pos_auth_headers, test_product) -> tuple[str, str, int, int]:
    """Create an invoice with one line item; return (invoice_id, line_item_id, total_cents, subtotal_cents)."""
    inv_resp = await client.post("/invoices", json={}, headers=pos_auth_headers)
    invoice_id = inv_resp.json()["id"]
    line_resp = await client.post(
        f"/invoices/{invoice_id}/line-items",
        json={"product_id": str(test_product.id), "quantity": 1},
        headers=pos_auth_headers,
    )
    line_item_id = line_resp.json()["id"]
    inv = (await client.get(f"/invoices/{invoice_id}", headers=pos_auth_headers)).json()
    return invoice_id, line_item_id, inv["total_cents"], inv["subtotal_cents"]


def _invoice_checksum(invoice_id, subtotal, tax, discount, total, line_items, payments) -> str:
    """Mirror invoice_service._build_invoice_checksum_payload() exactly for test-side computation."""
    return sha256_hex(
        {
            "invoice_id": invoice_id,
            "subtotal_cents": subtotal,
            "tax_cents": tax,
            "discount_cents": discount,
            "total_cents": total,
            "line_items": line_items,
            "payments": sorted(payments, key=lambda p: p["ref"]),
        }
    )


async def test_pay_invoice_client_ref_dedupes_retry(client, db, pos_auth_headers, test_product):
    """A retried pay call with the same client_ref does not record a duplicate payment leg."""
    invoice_id, _, total_cents, _ = await _open_invoice_with_line(client, pos_auth_headers, test_product)
    client_ref = str(uuid.uuid4())

    first = await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "cash", "amount_cents": total_cents, "client_ref": client_ref},
        headers=pos_auth_headers,
    )
    second = await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "cash", "amount_cents": total_cents, "client_ref": client_ref},
        headers=pos_auth_headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "paid"
    assert second.json()["status"] == "paid"

    payments = (
        await db.execute(select(Payment).where(Payment.invoice_id == uuid.UUID(invoice_id)))
    ).scalars().all()
    assert len(payments) == 1


async def test_pay_invoice_client_ref_dedupe_writes_one_audit_row(client, db, pos_auth_headers, test_product):
    """A deduped retried payment does not write a second INVOICE_PAID audit row."""
    invoice_id, _, total_cents, _ = await _open_invoice_with_line(client, pos_auth_headers, test_product)
    client_ref = str(uuid.uuid4())

    await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "cash", "amount_cents": total_cents, "client_ref": client_ref},
        headers=pos_auth_headers,
    )
    await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "cash", "amount_cents": total_cents, "client_ref": client_ref},
        headers=pos_auth_headers,
    )

    rows = (
        await db.execute(
            select(AuditLog).where(AuditLog.entity_id == invoice_id, AuditLog.action == INVOICE_PAID)
        )
    ).scalars().all()
    assert len(rows) == 1


async def test_pay_invoice_checksum_accepted_when_correct(client, pos_auth_headers, test_product):
    """A correctly-computed checksum is accepted and echoed back on the invoice."""
    invoice_id, line_item_id, total_cents, subtotal_cents = await _open_invoice_with_line(
        client, pos_auth_headers, test_product
    )
    payment_client_ref = str(uuid.uuid4())

    checksum = _invoice_checksum(
        invoice_id=invoice_id,
        subtotal=subtotal_cents,
        tax=0,
        discount=0,
        total=total_cents,
        line_items=[
            {
                "id": line_item_id,
                "product_id": str(test_product.id),
                "quantity": 1,
                "line_total_cents": subtotal_cents,
            }
        ],
        payments=[{"ref": payment_client_ref, "method": "cash", "amount_cents": total_cents}],
    )

    response = await client.post(
        f"/invoices/{invoice_id}/pay",
        json={
            "method": "cash",
            "amount_cents": total_cents,
            "client_ref": payment_client_ref,
            "checksum": checksum,
        },
        headers=pos_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["checksum"] == checksum


async def test_pay_invoice_checksum_mismatch_returns_422(client, pos_auth_headers, test_product):
    """A checksum that doesn't match the server's own computed digest is rejected."""
    invoice_id, _, total_cents, _ = await _open_invoice_with_line(client, pos_auth_headers, test_product)

    response = await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "cash", "amount_cents": total_cents, "checksum": "0" * 64},
        headers=pos_auth_headers,
    )

    assert response.status_code == 422


# ── Register session idempotency + checksum ──────────────────────────────────


async def test_open_session_client_ref_dedupes_retry(client, db, pos_auth_headers, test_device):
    """A retried open with the same client_ref returns the original session, not a 409."""
    existing = (
        await db.execute(select(RegisterSession).where(RegisterSession.device_id == test_device.id))
    ).scalar_one()
    await client.post(
        f"/register-sessions/{existing.id}/close",
        json={"closed_at": _iso(datetime.now(tz=timezone.utc)), "closing_cash_cents": 10000},
        headers=pos_auth_headers,
    )

    client_ref = str(uuid.uuid4())
    payload = {"opened_at": _iso(datetime.now(tz=timezone.utc)), "opening_cash_cents": 5000, "client_ref": client_ref}

    first = await client.post("/register-sessions/open", json=payload, headers=pos_auth_headers)
    second = await client.post("/register-sessions/open", json=payload, headers=pos_auth_headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    rows = (
        await db.execute(select(RegisterSession).where(RegisterSession.client_ref == client_ref))
    ).scalars().all()
    assert len(rows) == 1


async def test_open_session_client_ref_dedupe_writes_one_audit_row(client, db, pos_auth_headers, test_device):
    """A deduped retried open does not write a second REGISTER_SESSION_OPENED audit row."""
    existing = (
        await db.execute(select(RegisterSession).where(RegisterSession.device_id == test_device.id))
    ).scalar_one()
    await client.post(
        f"/register-sessions/{existing.id}/close",
        json={"closed_at": _iso(datetime.now(tz=timezone.utc)), "closing_cash_cents": 10000},
        headers=pos_auth_headers,
    )

    client_ref = str(uuid.uuid4())
    payload = {"opened_at": _iso(datetime.now(tz=timezone.utc)), "opening_cash_cents": 5000, "client_ref": client_ref}
    await client.post("/register-sessions/open", json=payload, headers=pos_auth_headers)
    resp = await client.post("/register-sessions/open", json=payload, headers=pos_auth_headers)
    session_id = resp.json()["id"]

    rows = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.entity_id == session_id, AuditLog.action == REGISTER_SESSION_OPENED
            )
        )
    ).scalars().all()
    assert len(rows) == 1


async def test_open_session_checksum_accepted_when_correct(client, db, pos_auth_headers, test_device):
    """A correctly-computed open checksum is accepted and echoed back."""
    existing = (
        await db.execute(select(RegisterSession).where(RegisterSession.device_id == test_device.id))
    ).scalar_one()
    await client.post(
        f"/register-sessions/{existing.id}/close",
        json={"closed_at": _iso(datetime.now(tz=timezone.utc)), "closing_cash_cents": 10000},
        headers=pos_auth_headers,
    )

    opened_at = datetime.now(tz=timezone.utc)
    checksum = sha256_hex(
        {"device_id": str(test_device.id), "opened_at": opened_at.isoformat(), "opening_cash_cents": 7500}
    )

    response = await client.post(
        "/register-sessions/open",
        json={"opened_at": _iso(opened_at), "opening_cash_cents": 7500, "checksum": checksum},
        headers=pos_auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["checksum"] == checksum


async def test_open_session_checksum_mismatch_returns_422(client, pos_auth_headers, test_device, db):
    """An incorrect open checksum is rejected."""
    existing = (
        await db.execute(select(RegisterSession).where(RegisterSession.device_id == test_device.id))
    ).scalar_one()
    await client.post(
        f"/register-sessions/{existing.id}/close",
        json={"closed_at": _iso(datetime.now(tz=timezone.utc)), "closing_cash_cents": 10000},
        headers=pos_auth_headers,
    )

    response = await client.post(
        "/register-sessions/open",
        json={
            "opened_at": _iso(datetime.now(tz=timezone.utc)),
            "opening_cash_cents": 7500,
            "checksum": "0" * 64,
        },
        headers=pos_auth_headers,
    )

    assert response.status_code == 422


async def test_close_session_client_ref_dedupes_retry(client, db, pos_auth_headers, test_device):
    """A retried close with the same client_ref returns the closed session instead of 400."""
    existing = (
        await db.execute(select(RegisterSession).where(RegisterSession.device_id == test_device.id))
    ).scalar_one()

    client_ref = str(uuid.uuid4())
    payload = {"closed_at": _iso(datetime.now(tz=timezone.utc)), "closing_cash_cents": 10000, "client_ref": client_ref}

    first = await client.post(f"/register-sessions/{existing.id}/close", json=payload, headers=pos_auth_headers)
    second = await client.post(f"/register-sessions/{existing.id}/close", json=payload, headers=pos_auth_headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["variance_cents"] == second.json()["variance_cents"]


async def test_close_session_different_client_ref_still_conflicts(client, db, pos_auth_headers, test_device):
    """A genuine second close (different/absent client_ref) still returns 400."""
    existing = (
        await db.execute(select(RegisterSession).where(RegisterSession.device_id == test_device.id))
    ).scalar_one()

    await client.post(
        f"/register-sessions/{existing.id}/close",
        json={"closed_at": _iso(datetime.now(tz=timezone.utc)), "closing_cash_cents": 10000, "client_ref": "a"},
        headers=pos_auth_headers,
    )
    response = await client.post(
        f"/register-sessions/{existing.id}/close",
        json={"closed_at": _iso(datetime.now(tz=timezone.utc)), "closing_cash_cents": 10000, "client_ref": "b"},
        headers=pos_auth_headers,
    )

    assert response.status_code == 400


async def test_close_session_checksum_mismatch_returns_422(client, db, pos_auth_headers, test_device):
    """An incorrect close checksum is rejected and the session stays open."""
    existing = (
        await db.execute(select(RegisterSession).where(RegisterSession.device_id == test_device.id))
    ).scalar_one()

    response = await client.post(
        f"/register-sessions/{existing.id}/close",
        json={
            "closed_at": _iso(datetime.now(tz=timezone.utc)),
            "closing_cash_cents": 10000,
            "checksum": "0" * 64,
        },
        headers=pos_auth_headers,
    )

    assert response.status_code == 422

    await db.refresh(existing)
    assert existing.status == "open"
