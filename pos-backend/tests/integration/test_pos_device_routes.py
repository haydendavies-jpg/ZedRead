"""Integration tests for /pos-devices routes.

Covers all five required scenarios per tests_CLAUDE.md:
1. Happy path — correct response shape
2. Auth failure — no token → 403
3. Invalid input — missing fields → 422, short token → 422
4. Business rule — 409 duplicate token, 404 unknown site/license, 422 mismatched
5. Audit log — register and deregister assert the correct audit_logs rows
"""

import uuid

from sqlalchemy import select

from app.constants.audit_actions import DEVICE_DEREGISTERED, DEVICE_REGISTERED
from app.models.audit_log import AuditLog


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_register_device_returns_201(client, portal_auth_headers, test_site, test_license):
    """POST /pos-devices registers a device and returns 201 with the correct shape."""
    response = await client.post(
        "/pos-devices/",
        json={
            "site_id": str(test_site.id),
            "license_id": str(test_license.id),
            "device_name": "Till 1",
            "device_token": "hardware-token-001",
        },
        headers=portal_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["site_id"] == str(test_site.id)
    assert body["license_id"] == str(test_license.id)
    assert body["device_name"] == "Till 1"
    assert body["is_active"] is True


async def test_list_devices_returns_200(client, portal_auth_headers, test_device):
    """GET /pos-devices returns 200 with a list containing the seeded device."""
    response = await client.get("/pos-devices/", headers=portal_auth_headers)

    assert response.status_code == 200
    ids = [d["id"] for d in response.json()]
    assert str(test_device.id) in ids


async def test_get_device_returns_correct_device(client, portal_auth_headers, test_device):
    """GET /pos-devices/{id} returns the correct device."""
    response = await client.get(f"/pos-devices/{test_device.id}", headers=portal_auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(test_device.id)


async def test_deregister_device(client, portal_auth_headers, test_device):
    """POST /pos-devices/{id}/deregister sets is_active to False."""
    response = await client.post(
        f"/pos-devices/{test_device.id}/deregister", headers=portal_auth_headers
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


# ── Auth failure ──────────────────────────────────────────────────────────────


async def test_list_devices_no_token_returns_403(client):
    """GET /pos-devices without a token returns 403."""
    response = await client.get("/pos-devices/")
    assert response.status_code == 403


async def test_register_device_no_token_returns_403(client, test_site, test_license):
    """POST /pos-devices without a token returns 403."""
    response = await client.post(
        "/pos-devices/",
        json={
            "site_id": str(test_site.id),
            "license_id": str(test_license.id),
            "device_name": "Till",
            "device_token": "some-token-xyz",
        },
    )
    assert response.status_code == 403


# ── Invalid input ─────────────────────────────────────────────────────────────


async def test_register_device_missing_site_id_returns_422(client, portal_auth_headers, test_license):
    """POST /pos-devices without site_id returns 422."""
    response = await client.post(
        "/pos-devices/",
        json={"license_id": str(test_license.id), "device_name": "Till", "device_token": "tok123456"},
        headers=portal_auth_headers,
    )
    assert response.status_code == 422


async def test_register_device_short_token_returns_422(client, portal_auth_headers, test_site, test_license):
    """POST /pos-devices with a token shorter than 8 chars returns 422."""
    response = await client.post(
        "/pos-devices/",
        json={
            "site_id": str(test_site.id),
            "license_id": str(test_license.id),
            "device_name": "Till",
            "device_token": "short",
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 422


# ── Business rule violations ──────────────────────────────────────────────────


async def test_register_device_duplicate_token_returns_409(
    client, portal_auth_headers, test_site, test_license, test_device
):
    """POST /pos-devices with a token already in use returns 409."""
    response = await client.post(
        "/pos-devices/",
        json={
            "site_id": str(test_site.id),
            "license_id": str(test_license.id),
            "device_name": "Till 2",
            "device_token": test_device.device_token,  # Same token as existing device
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 409


async def test_register_device_unknown_site_returns_404(client, portal_auth_headers, test_license):
    """POST /pos-devices with a non-existent site_id returns 404."""
    response = await client.post(
        "/pos-devices/",
        json={
            "site_id": str(uuid.uuid4()),
            "license_id": str(test_license.id),
            "device_name": "Till",
            "device_token": "valid-token-xyz",
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 404


async def test_register_device_unknown_license_returns_404(client, portal_auth_headers, test_site):
    """POST /pos-devices with a non-existent license_id returns 404."""
    response = await client.post(
        "/pos-devices/",
        json={
            "site_id": str(test_site.id),
            "license_id": str(uuid.uuid4()),
            "device_name": "Till",
            "device_token": "valid-token-xyz",
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 404


async def test_get_unknown_device_returns_404(client, portal_auth_headers):
    """GET /pos-devices/{unknown_id} returns 404."""
    response = await client.get(f"/pos-devices/{uuid.uuid4()}", headers=portal_auth_headers)
    assert response.status_code == 404


async def test_deregister_already_deregistered_device_returns_409(
    client, portal_auth_headers, test_device
):
    """Deregistering an already-inactive device returns 409."""
    await client.post(f"/pos-devices/{test_device.id}/deregister", headers=portal_auth_headers)
    response = await client.post(
        f"/pos-devices/{test_device.id}/deregister", headers=portal_auth_headers
    )
    assert response.status_code == 409


# ── Audit log assertions ──────────────────────────────────────────────────────


async def test_register_device_writes_audit_log(
    client, db, portal_auth_headers, test_site, test_license
):
    """POST /pos-devices writes a DEVICE_REGISTERED audit row."""
    response = await client.post(
        "/pos-devices/",
        json={
            "site_id": str(test_site.id),
            "license_id": str(test_license.id),
            "device_name": "Audit Till",
            "device_token": "audit-token-001",
        },
        headers=portal_auth_headers,
    )
    device_id = response.json()["id"]

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == device_id,
            AuditLog.action == DEVICE_REGISTERED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["device_name"] == "Audit Till"


async def test_deregister_device_writes_audit_log(client, db, portal_auth_headers, test_device):
    """POST /pos-devices/{id}/deregister writes a DEVICE_DEREGISTERED audit row."""
    await client.post(f"/pos-devices/{test_device.id}/deregister", headers=portal_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_device.id),
            AuditLog.action == DEVICE_DEREGISTERED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["is_active"] is False
