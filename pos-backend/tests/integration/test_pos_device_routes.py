"""Integration tests for /pos-devices routes.

Covers all five required scenarios per tests_CLAUDE.md:
1. Happy path — correct response shape
2. Auth failure — no token → 403
3. Invalid input — missing fields → 422, short token → 422
4. Business rule — 409 duplicate token, 404 unknown site/license, 422 mismatched
5. Audit log — register and deregister assert the correct audit_logs rows
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.constants.audit_actions import DEVICE_DEREGISTERED, DEVICE_REGISTERED, DEVICE_RENAMED
from app.models.access_profile_page_permission import AccessProfilePagePermission
from app.models.audit_log import AuditLog
from app.models.license import License
from app.models.pos_device import PosDevice
from app.models.site import Site


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


# ── GET /pos-devices/management (scoped list) ──────────────────────────────────


async def test_list_devices_management_returns_200(client, mgmt_auth_headers, test_device):
    """GET /pos-devices/management returns 200 with devices in the caller's scope."""
    response = await client.get("/pos-devices/management", headers=mgmt_auth_headers)

    assert response.status_code == 200
    ids = [d["id"] for d in response.json()]
    assert str(test_device.id) in ids


async def test_list_devices_management_no_token_returns_403(client):
    """GET /pos-devices/management without a token returns 403."""
    response = await client.get("/pos-devices/management")
    assert response.status_code == 403


async def test_list_devices_management_site_scope_excludes_other_sites(
    client, db, mgmt_auth_headers, test_site, test_brand, test_license
):
    """A site-scope caller never sees a device registered to a different site."""
    other_site = Site(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        name="Other Site",
        is_active=True,
        timezone="Australia/Sydney",
        currency="AUD",
        country="AU",
        address_street="9 Other Street",
        address_state="NSW",
        address_postcode="2000",
    )
    db.add(other_site)
    await db.flush()

    other_license = License(
        id=uuid.uuid4(),
        site_id=other_site.id,
        plan_name="starter",
        status="active",
        monthly_fee_cents=0,
        is_trial=False,
        max_devices=1,
        starts_at=datetime.now(tz=timezone.utc),
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=365),
    )
    db.add(other_license)

    other_device = PosDevice(
        id=uuid.uuid4(),
        site_id=other_site.id,
        license_id=other_license.id,
        device_name="Other Site Terminal",
        device_token="other-site-token-xyz",
        is_active=True,
    )
    db.add(other_device)
    await db.commit()

    response = await client.get("/pos-devices/management", headers=mgmt_auth_headers)

    assert response.status_code == 200
    ids = [d["id"] for d in response.json()]
    assert str(other_device.id) not in ids


# ── POST /pos-devices/{id}/release ─────────────────────────────────────────────


async def test_release_device_without_permission_returns_403(client, mgmt_auth_headers, test_device):
    """A management caller whose access profile lacks the 'devices' page permission is denied."""
    response = await client.post(f"/pos-devices/{test_device.id}/release", headers=mgmt_auth_headers)
    assert response.status_code == 403


async def test_release_device_with_permission_succeeds(
    client, db, mgmt_auth_headers, test_manager_profile, test_device
):
    """A management caller granted the 'devices' page permission can release a device in scope."""
    db.add(AccessProfilePagePermission(id=uuid.uuid4(), access_profile_id=test_manager_profile.id, page_key="devices"))
    await db.commit()

    response = await client.post(f"/pos-devices/{test_device.id}/release", headers=mgmt_auth_headers)

    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_release_device_outside_site_scope_returns_403(
    client, db, mgmt_auth_headers, test_manager_profile, test_brand
):
    """A site-scope caller cannot release a device registered to a different site, even with permission."""
    db.add(AccessProfilePagePermission(id=uuid.uuid4(), access_profile_id=test_manager_profile.id, page_key="devices"))

    other_site = Site(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        name="Other Site",
        is_active=True,
        timezone="Australia/Sydney",
        currency="AUD",
        country="AU",
        address_street="9 Other Street",
        address_state="NSW",
        address_postcode="2000",
    )
    db.add(other_site)
    await db.flush()

    other_license = License(
        id=uuid.uuid4(),
        site_id=other_site.id,
        plan_name="starter",
        status="active",
        monthly_fee_cents=0,
        is_trial=False,
        max_devices=1,
        starts_at=datetime.now(tz=timezone.utc),
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=365),
    )
    db.add(other_license)

    other_device = PosDevice(
        id=uuid.uuid4(),
        site_id=other_site.id,
        license_id=other_license.id,
        device_name="Other Site Terminal",
        device_token="other-site-token-abc",
        is_active=True,
    )
    db.add(other_device)
    await db.commit()

    response = await client.post(f"/pos-devices/{other_device.id}/release", headers=mgmt_auth_headers)
    assert response.status_code == 403


async def test_release_device_pos_access_forbidden(client, pos_auth_headers, test_device):
    """A raw POS terminal session can never release a device seat."""
    response = await client.post(f"/pos-devices/{test_device.id}/release", headers=pos_auth_headers)
    assert response.status_code == 403


async def test_release_device_portal_admin_always_permitted(client, portal_auth_headers, test_device):
    """A portal admin (superadmin) may release any device, regardless of page permissions."""
    response = await client.post(f"/pos-devices/{test_device.id}/release", headers=portal_auth_headers)
    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_release_device_writes_audit_log(
    client, db, mgmt_auth_headers, test_manager_profile, test_device
):
    """A successful release writes a DEVICE_DEREGISTERED audit row attributed to the caller."""
    db.add(AccessProfilePagePermission(id=uuid.uuid4(), access_profile_id=test_manager_profile.id, page_key="devices"))
    await db.commit()

    await client.post(f"/pos-devices/{test_device.id}/release", headers=mgmt_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_device.id),
            AuditLog.action == DEVICE_DEREGISTERED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["is_active"] is False


# ── PATCH /pos-devices/{id} (rename) ────────────────────────────────────────────


async def test_rename_device_without_permission_returns_403(client, mgmt_auth_headers, test_device):
    """A management caller whose access profile lacks the 'devices' page permission is denied."""
    response = await client.patch(
        f"/pos-devices/{test_device.id}", json={"device_name": "POS #7"}, headers=mgmt_auth_headers
    )
    assert response.status_code == 403


async def test_rename_device_with_permission_succeeds(
    client, db, mgmt_auth_headers, test_manager_profile, test_device
):
    """A management caller granted the 'devices' page permission can rename a device in scope."""
    db.add(AccessProfilePagePermission(id=uuid.uuid4(), access_profile_id=test_manager_profile.id, page_key="devices"))
    await db.commit()

    response = await client.patch(
        f"/pos-devices/{test_device.id}", json={"device_name": "POS #7"}, headers=mgmt_auth_headers
    )

    assert response.status_code == 200
    assert response.json()["device_name"] == "POS #7"


async def test_rename_device_outside_site_scope_returns_403(
    client, db, mgmt_auth_headers, test_manager_profile, test_brand
):
    """A site-scope caller cannot rename a device registered to a different site, even with permission."""
    db.add(AccessProfilePagePermission(id=uuid.uuid4(), access_profile_id=test_manager_profile.id, page_key="devices"))

    other_site = Site(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        name="Other Site",
        is_active=True,
        timezone="Australia/Sydney",
        currency="AUD",
        country="AU",
        address_street="9 Other Street",
        address_state="NSW",
        address_postcode="2000",
    )
    db.add(other_site)
    await db.flush()

    other_license = License(
        id=uuid.uuid4(),
        site_id=other_site.id,
        plan_name="starter",
        status="active",
        monthly_fee_cents=0,
        is_trial=False,
        max_devices=1,
        starts_at=datetime.now(tz=timezone.utc),
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=365),
    )
    db.add(other_license)

    other_device = PosDevice(
        id=uuid.uuid4(),
        site_id=other_site.id,
        license_id=other_license.id,
        device_name="Other Site Terminal",
        device_token="other-site-token-rnm",
        is_active=True,
    )
    db.add(other_device)
    await db.commit()

    response = await client.patch(
        f"/pos-devices/{other_device.id}", json={"device_name": "Hijacked"}, headers=mgmt_auth_headers
    )
    assert response.status_code == 403


async def test_rename_device_pos_access_forbidden(client, pos_auth_headers, test_device):
    """A raw POS terminal session can never rename a device."""
    response = await client.patch(
        f"/pos-devices/{test_device.id}", json={"device_name": "Hijacked"}, headers=pos_auth_headers
    )
    assert response.status_code == 403


async def test_rename_device_portal_admin_always_permitted(client, portal_auth_headers, test_device):
    """A portal admin (superadmin) may rename any device, regardless of page permissions."""
    response = await client.patch(
        f"/pos-devices/{test_device.id}", json={"device_name": "Renamed by admin"}, headers=portal_auth_headers
    )
    assert response.status_code == 200
    assert response.json()["device_name"] == "Renamed by admin"


async def test_rename_device_blank_name_returns_422(client, portal_auth_headers, test_device):
    """PATCH /pos-devices/{id} with an empty device_name returns 422."""
    response = await client.patch(
        f"/pos-devices/{test_device.id}", json={"device_name": ""}, headers=portal_auth_headers
    )
    assert response.status_code == 422


async def test_rename_unknown_device_returns_404(client, portal_auth_headers):
    """PATCH /pos-devices/{unknown_id} returns 404."""
    response = await client.patch(
        f"/pos-devices/{uuid.uuid4()}", json={"device_name": "Ghost"}, headers=portal_auth_headers
    )
    assert response.status_code == 404


async def test_rename_device_writes_audit_log(client, db, portal_auth_headers, test_device):
    """A successful rename writes a DEVICE_RENAMED audit row with before/after names."""
    original_name = test_device.device_name

    await client.patch(
        f"/pos-devices/{test_device.id}", json={"device_name": "Front Counter"}, headers=portal_auth_headers
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_device.id),
            AuditLog.action == DEVICE_RENAMED,
        )
    )
    row = result.scalar_one()
    assert row.before_state["device_name"] == original_name
    assert row.after_state["device_name"] == "Front Counter"
