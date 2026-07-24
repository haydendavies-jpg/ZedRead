"""Integration tests for /printer-locations routes.

Covers:
1. Happy path — create/list/update a printer location, docket template auto-created
2. Auth failure — no token → 401/403; POS token returns 403 on writes
3. Invalid input — missing required fields, copy_count < 1 → 422
4. Business rules — n/a beyond validation (no cross-brand FK on create)
5. Audit log — PRINTER_LOCATION_CREATED, PRINTER_LOCATION_UPDATED, PRINTER_LOCATION_DEACTIVATED
"""

import uuid

import pytest
from sqlalchemy import select

from app.constants.audit_actions import (
    PRINTER_LOCATION_CREATED,
    PRINTER_LOCATION_DEACTIVATED,
    PRINTER_LOCATION_UPDATED,
)
from app.models.audit_log import AuditLog
from app.models.print_template import PrintTemplate

pytestmark = pytest.mark.asyncio


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_create_printer_location_returns_201(client, mgmt_auth_headers):
    """POST /printer-locations creates a location and returns 201 with the correct shape."""
    response = await client.post(
        "/printer-locations", json={"name": "Kitchen", "copy_count": 2}, headers=mgmt_auth_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Kitchen"
    assert body["copy_count"] == 2
    assert body["is_active"] is True
    assert body["ref"].startswith("PRN-")


async def test_create_printer_location_defaults_copy_count_to_one(client, mgmt_auth_headers):
    """POST /printer-locations without copy_count defaults to 1."""
    response = await client.post("/printer-locations", json={"name": "Bar"}, headers=mgmt_auth_headers)
    assert response.status_code == 201
    assert response.json()["copy_count"] == 1


async def test_create_printer_location_auto_creates_docket_template(client, db, mgmt_auth_headers):
    """Creating a printer location auto-creates its own 'docket' print template."""
    response = await client.post("/printer-locations", json={"name": "Grill"}, headers=mgmt_auth_headers)
    location_id = response.json()["id"]

    result = await db.execute(
        select(PrintTemplate).where(
            PrintTemplate.printer_location_id == uuid.UUID(location_id),
            PrintTemplate.template_type == "docket",
        )
    )
    template = result.scalar_one()
    assert template.name == "Grill Docket"


async def test_list_printer_locations_returns_200(client, mgmt_auth_headers):
    """GET /printer-locations returns 200 with the created location."""
    create_resp = await client.post("/printer-locations", json={"name": "Pastry"}, headers=mgmt_auth_headers)
    location_id = create_resp.json()["id"]

    response = await client.get("/printer-locations", headers=mgmt_auth_headers)

    assert response.status_code == 200
    ids = [loc["id"] for loc in response.json()]
    assert location_id in ids


async def test_update_printer_location_renames(client, mgmt_auth_headers):
    """PATCH /printer-locations/{id} updates name and copy_count."""
    create_resp = await client.post("/printer-locations", json={"name": "Fryer"}, headers=mgmt_auth_headers)
    location_id = create_resp.json()["id"]

    response = await client.patch(
        f"/printer-locations/{location_id}",
        json={"name": "Deep Fryer", "copy_count": 3},
        headers=mgmt_auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Deep Fryer"
    assert body["copy_count"] == 3


# ── Auth failure ──────────────────────────────────────────────────────────────


async def test_create_printer_location_no_token_returns_403(client):
    """POST /printer-locations with no auth token returns 403."""
    response = await client.post("/printer-locations", json={"name": "Kitchen"})
    assert response.status_code == 403


async def test_create_printer_location_pos_token_returns_403(client, pos_auth_headers):
    """POST /printer-locations with a POS terminal token returns 403."""
    response = await client.post("/printer-locations", json={"name": "Kitchen"}, headers=pos_auth_headers)
    assert response.status_code == 403


# ── Invalid input ─────────────────────────────────────────────────────────────


async def test_create_printer_location_missing_name_returns_422(client, mgmt_auth_headers):
    """POST /printer-locations without a name returns 422."""
    response = await client.post("/printer-locations", json={}, headers=mgmt_auth_headers)
    assert response.status_code == 422


async def test_create_printer_location_zero_copy_count_returns_422(client, mgmt_auth_headers):
    """POST /printer-locations with copy_count=0 returns 422 (must be >= 1)."""
    response = await client.post(
        "/printer-locations", json={"name": "Kitchen", "copy_count": 0}, headers=mgmt_auth_headers
    )
    assert response.status_code == 422


# ── Audit log ─────────────────────────────────────────────────────────────────


async def test_create_printer_location_writes_audit_log(client, db, mgmt_auth_headers):
    """Creating a printer location writes a PRINTER_LOCATION_CREATED audit row."""
    response = await client.post("/printer-locations", json={"name": "Salad Station"}, headers=mgmt_auth_headers)
    location_id = response.json()["id"]

    audit = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == location_id,
            AuditLog.action == PRINTER_LOCATION_CREATED,
        )
    )
    assert audit.scalar_one() is not None


async def test_update_printer_location_writes_audit_log(client, db, mgmt_auth_headers):
    """Renaming a printer location writes a PRINTER_LOCATION_UPDATED audit row."""
    create_resp = await client.post("/printer-locations", json={"name": "Dessert"}, headers=mgmt_auth_headers)
    location_id = create_resp.json()["id"]

    await client.patch(f"/printer-locations/{location_id}", json={"name": "Desserts"}, headers=mgmt_auth_headers)

    audit = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == location_id,
            AuditLog.action == PRINTER_LOCATION_UPDATED,
        )
    )
    assert audit.scalar_one() is not None


async def test_deactivate_printer_location_writes_deactivated_audit_log(client, db, mgmt_auth_headers):
    """Setting is_active=False alone writes PRINTER_LOCATION_DEACTIVATED, not PRINTER_LOCATION_UPDATED."""
    create_resp = await client.post("/printer-locations", json={"name": "Expo"}, headers=mgmt_auth_headers)
    location_id = create_resp.json()["id"]

    response = await client.patch(
        f"/printer-locations/{location_id}", json={"is_active": False}, headers=mgmt_auth_headers
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    audit = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == location_id,
            AuditLog.action == PRINTER_LOCATION_DEACTIVATED,
        )
    )
    assert audit.scalar_one() is not None
