"""Integration tests for register (till) session reporting routes.

Covers: happy path (POS-opened session visible to the portal report), the
management-portal view of the same data, filters (status/site/device/date),
site-scope enforcement for a site-scoped management caller, auth failure,
and invalid input.
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


# ── Happy path ─────────────────────────────────────────────────────────────


async def test_list_register_session_reports_happy_path(
    client: AsyncClient, pos_auth_headers: dict, test_device, test_site
) -> None:
    """GET /register-session-reports returns the device's open session, most recently opened first."""
    resp = await client.get("/register-session-reports", headers=pos_auth_headers)

    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["device_id"] == str(test_device.id)
    assert row["device_name"] == test_device.device_name
    assert row["site_id"] == str(test_site.id)
    assert row["status"] == "open"
    assert row["opening_cash_cents"] == 10000
    assert row["closed_at"] is None
    assert row["variance_cents"] is None
    assert row["cash_takings_cents"] is None


async def test_list_register_session_reports_visible_to_management_portal(
    client: AsyncClient, pos_auth_headers: dict, mgmt_auth_headers: dict
) -> None:
    """A site-scope management caller sees the same session a POS caller opened."""
    resp = await client.get("/register-session-reports", headers=mgmt_auth_headers)

    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_list_register_session_reports_reflects_closed_session(
    client: AsyncClient, db: AsyncSession, pos_auth_headers: dict
) -> None:
    """After closing, the report row shows closing cash, expected cash, takings, and variance."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.models.register_session import RegisterSession

    session = (await db.execute(select(RegisterSession))).scalar_one()
    close_resp = await client.post(
        f"/register-sessions/{session.id}/close",
        json={"closed_at": datetime.now(tz=timezone.utc).isoformat(), "closing_cash_cents": 10500},
        headers=pos_auth_headers,
    )
    assert close_resp.status_code == 200

    resp = await client.get("/register-session-reports", headers=pos_auth_headers)
    assert resp.status_code == 200
    row = resp.json()[0]
    assert row["status"] == "closed"
    assert row["closing_cash_cents"] == 10500
    assert row["expected_cash_cents"] == 10000
    assert row["cash_takings_cents"] == 0
    assert row["variance_cents"] == 500
    assert row["closed_by_name"] is not None


# ── Filters ────────────────────────────────────────────────────────────────


async def test_list_register_session_reports_status_filter(
    client: AsyncClient, pos_auth_headers: dict
) -> None:
    """?status=closed excludes the still-open session."""
    resp = await client.get(
        "/register-session-reports", params={"status": "closed"}, headers=pos_auth_headers
    )

    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_register_session_reports_device_filter_excludes_other_device(
    client: AsyncClient, pos_auth_headers: dict
) -> None:
    """A device_id that doesn't match any session returns an empty list."""
    resp = await client.get(
        "/register-session-reports",
        params={"device_id": "00000000-0000-0000-0000-000000000000"},
        headers=pos_auth_headers,
    )

    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_register_session_reports_date_range_filter(
    client: AsyncClient, pos_auth_headers: dict
) -> None:
    """A start_date in the future excludes the session opened today."""
    future = (date.today() + timedelta(days=1)).isoformat()
    resp = await client.get(
        "/register-session-reports", params={"start_date": future}, headers=pos_auth_headers
    )

    assert resp.status_code == 200
    assert resp.json() == []


# ── Site-scope enforcement ────────────────────────────────────────────────


async def test_list_register_session_reports_site_scope_caller_cannot_query_other_site(
    client: AsyncClient, mgmt_auth_headers: dict
) -> None:
    """A site-scope management caller requesting a different site_id is rejected with 403."""
    resp = await client.get(
        "/register-session-reports",
        params={"site_id": "00000000-0000-0000-0000-000000000000"},
        headers=mgmt_auth_headers,
    )

    assert resp.status_code == 403


# ── Auth / validation ──────────────────────────────────────────────────────


async def test_list_register_session_reports_requires_authentication(client: AsyncClient) -> None:
    """No token returns 403."""
    resp = await client.get("/register-session-reports")

    assert resp.status_code == 403


async def test_list_register_session_reports_limit_over_max_returns_422(
    client: AsyncClient, pos_auth_headers: dict
) -> None:
    """limit above the 1000 cap fails validation."""
    resp = await client.get(
        "/register-session-reports", params={"limit": 2000}, headers=pos_auth_headers
    )

    assert resp.status_code == 422
