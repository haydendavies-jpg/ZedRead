"""Integration tests for POS register (till) session routes.

Covers:
1. Happy path — open, close (with computed variance), current-session lookup
2. Auth failure — no token
3. Invalid input — missing fields return 422
4. Business rules — double-open rejected, close-when-closed rejected,
   invoice creation blocked without an open session
5. Audit log — open and close both write correct rows
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.constants.audit_actions import REGISTER_SESSION_CLOSED, REGISTER_SESSION_OPENED
from app.models.audit_log import AuditLog
from app.models.register_session import RegisterSession

pytestmark = pytest.mark.asyncio


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ── Open ───────────────────────────────────────────────────────────────────


async def test_open_session_returns_201(client, pos_auth_headers, test_device, db):
    """Opening a session succeeds and returns the created row.

    pos_auth_headers already opens one session for test_device (see
    conftest.py), so this test closes it first to exercise a clean open.
    """
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
            "opening_cash_cents": 20000,
        },
        headers=pos_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "open"
    assert body["opening_cash_cents"] == 20000
    assert body["device_id"] == str(test_device.id)
    assert body["opened_by_name"] == "Test POS User"


async def test_open_session_writes_audit_log(client, db, pos_auth_headers, test_device):
    """Opening a session writes a REGISTER_SESSION_OPENED audit row."""
    existing = (
        await db.execute(select(RegisterSession).where(RegisterSession.device_id == test_device.id))
    ).scalar_one()
    await client.post(
        f"/register-sessions/{existing.id}/close",
        json={"closed_at": _iso(datetime.now(tz=timezone.utc)), "closing_cash_cents": 10000},
        headers=pos_auth_headers,
    )

    resp = await client.post(
        "/register-sessions/open",
        json={"opened_at": _iso(datetime.now(tz=timezone.utc)), "opening_cash_cents": 15000},
        headers=pos_auth_headers,
    )
    session_id = resp.json()["id"]

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == session_id,
            AuditLog.action == REGISTER_SESSION_OPENED,
        )
    )
    row = result.scalar_one()
    assert row.actor_email == "posuser@test.com"


async def test_open_session_already_open_returns_409(client, pos_auth_headers):
    """A device with an already-open session (from pos_auth_headers) rejects a second open with 409."""
    response = await client.post(
        "/register-sessions/open",
        json={"opened_at": _iso(datetime.now(tz=timezone.utc)), "opening_cash_cents": 5000},
        headers=pos_auth_headers,
    )

    assert response.status_code == 409


async def test_open_session_missing_fields_returns_422(client, pos_auth_headers):
    """Missing opening_cash_cents returns 422."""
    response = await client.post(
        "/register-sessions/open",
        json={"opened_at": _iso(datetime.now(tz=timezone.utc))},
        headers=pos_auth_headers,
    )

    assert response.status_code == 422


async def test_open_session_requires_authentication(client):
    """Open without a token returns 403."""
    response = await client.post(
        "/register-sessions/open",
        json={"opened_at": _iso(datetime.now(tz=timezone.utc)), "opening_cash_cents": 5000},
    )

    assert response.status_code == 403


# ── Current ────────────────────────────────────────────────────────────────


async def test_get_current_session_returns_open_session(client, pos_auth_headers, test_device):
    """GET /register-sessions/current returns the device's open session."""
    response = await client.get("/register-sessions/current", headers=pos_auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body is not None
    assert body["device_id"] == str(test_device.id)
    assert body["status"] == "open"


async def test_get_current_session_returns_null_when_closed(client, db, pos_auth_headers, test_device):
    """GET /register-sessions/current returns null once the session is closed."""
    existing = (
        await db.execute(select(RegisterSession).where(RegisterSession.device_id == test_device.id))
    ).scalar_one()
    await client.post(
        f"/register-sessions/{existing.id}/close",
        json={"closed_at": _iso(datetime.now(tz=timezone.utc)), "closing_cash_cents": 10000},
        headers=pos_auth_headers,
    )

    response = await client.get("/register-sessions/current", headers=pos_auth_headers)

    assert response.status_code == 200
    assert response.json() is None


# ── Close ──────────────────────────────────────────────────────────────────


async def test_close_session_computes_expected_variance_no_sales(client, db, pos_auth_headers, test_device):
    """With no cash sales recorded, expected == opening and variance == closing - opening."""
    existing = (
        await db.execute(select(RegisterSession).where(RegisterSession.device_id == test_device.id))
    ).scalar_one()
    assert existing.opening_cash_cents == 10000  # seeded by pos_auth_headers

    response = await client.post(
        f"/register-sessions/{existing.id}/close",
        json={"closed_at": _iso(datetime.now(tz=timezone.utc)), "closing_cash_cents": 9500},
        headers=pos_auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "closed"
    assert body["expected_cash_cents"] == 10000
    assert body["variance_cents"] == -500


async def test_close_session_includes_cash_sales_in_expected(client, db, pos_auth_headers, test_product):
    """Cash payments recorded against invoices under the session count toward expected cash."""
    create_resp = await client.post("/invoices", json={}, headers=pos_auth_headers)
    invoice_id = create_resp.json()["id"]
    await client.post(
        f"/invoices/{invoice_id}/line-items",
        json={"product_id": str(test_product.id), "quantity": 1},
        headers=pos_auth_headers,
    )
    pay_resp = await client.get(f"/invoices/{invoice_id}", headers=pos_auth_headers)
    total_cents = pay_resp.json()["total_cents"]
    await client.post(
        f"/invoices/{invoice_id}/pay",
        json={"method": "cash", "amount_cents": total_cents},
        headers=pos_auth_headers,
    )

    session = (
        await db.execute(select(RegisterSession).where(RegisterSession.status == "open"))
    ).scalar_one()

    response = await client.post(
        f"/register-sessions/{session.id}/close",
        json={"closed_at": _iso(datetime.now(tz=timezone.utc)), "closing_cash_cents": 10000 + total_cents},
        headers=pos_auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["expected_cash_cents"] == 10000 + total_cents
    assert body["variance_cents"] == 0


async def test_close_session_writes_audit_log(client, db, pos_auth_headers, test_device):
    """Closing a session writes a REGISTER_SESSION_CLOSED audit row."""
    existing = (
        await db.execute(select(RegisterSession).where(RegisterSession.device_id == test_device.id))
    ).scalar_one()

    await client.post(
        f"/register-sessions/{existing.id}/close",
        json={"closed_at": _iso(datetime.now(tz=timezone.utc)), "closing_cash_cents": 10000},
        headers=pos_auth_headers,
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(existing.id),
            AuditLog.action == REGISTER_SESSION_CLOSED,
        )
    )
    row = result.scalar_one()
    assert row.actor_email == "posuser@test.com"


async def test_close_already_closed_session_returns_400(client, db, pos_auth_headers, test_device):
    """Closing an already-closed session returns 400."""
    existing = (
        await db.execute(select(RegisterSession).where(RegisterSession.device_id == test_device.id))
    ).scalar_one()
    await client.post(
        f"/register-sessions/{existing.id}/close",
        json={"closed_at": _iso(datetime.now(tz=timezone.utc)), "closing_cash_cents": 10000},
        headers=pos_auth_headers,
    )

    response = await client.post(
        f"/register-sessions/{existing.id}/close",
        json={"closed_at": _iso(datetime.now(tz=timezone.utc)), "closing_cash_cents": 10000},
        headers=pos_auth_headers,
    )

    assert response.status_code == 400


async def test_close_unknown_session_returns_404(client, pos_auth_headers):
    """Closing a session ID that doesn't exist returns 404."""
    response = await client.post(
        "/register-sessions/00000000-0000-0000-0000-000000000000/close",
        json={"closed_at": _iso(datetime.now(tz=timezone.utc)), "closing_cash_cents": 10000},
        headers=pos_auth_headers,
    )

    assert response.status_code == 404


# ── Invoice creation gating ───────────────────────────────────────────────


async def test_create_invoice_without_open_session_returns_400(client, db, pos_auth_headers, test_device):
    """Invoice creation is rejected with 400 once the device's till is closed."""
    existing = (
        await db.execute(select(RegisterSession).where(RegisterSession.device_id == test_device.id))
    ).scalar_one()
    await client.post(
        f"/register-sessions/{existing.id}/close",
        json={"closed_at": _iso(datetime.now(tz=timezone.utc)), "closing_cash_cents": 10000},
        headers=pos_auth_headers,
    )

    response = await client.post("/invoices", json={}, headers=pos_auth_headers)

    assert response.status_code == 400
    assert "register session" in response.json()["detail"].lower()


async def test_create_invoice_sets_register_session_id(client, db, pos_auth_headers, test_device):
    """A created invoice is attributed to the device's open register session."""
    existing = (
        await db.execute(select(RegisterSession).where(RegisterSession.device_id == test_device.id))
    ).scalar_one()

    response = await client.post("/invoices", json={}, headers=pos_auth_headers)

    assert response.status_code == 201
    assert response.json()["register_session_id"] == str(existing.id)
