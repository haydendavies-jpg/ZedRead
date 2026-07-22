"""Integration tests for /licenses routes.

Covers all five required scenarios per tests_CLAUDE.md:
1. Happy path — correct response shape
2. Auth failure — no token → 403
3. Invalid input — missing fields → 422
4. Business rule — 404 for unknown site, 409 for duplicate license
5. Audit log — every write asserts the correct audit_logs row
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.constants.audit_actions import LICENSE_CREATED, LICENSE_DISABLED, LICENSE_ENABLED, LICENSE_UPDATED
from app.models.access_profile_page_permission import AccessProfilePagePermission
from app.models.audit_log import AuditLog
from app.models.brand import Brand
from app.models.license import License
from app.models.site import Site


def _future_dates() -> dict:
    """Return a valid starts_at / expires_at pair for use in POST payloads."""
    now = datetime.now(tz=timezone.utc)
    return {
        "starts_at": now.isoformat(),
        "expires_at": (now + timedelta(days=365)).isoformat(),
    }


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_create_license_returns_201(client, portal_auth_headers, test_site):
    """POST /licenses creates a license and returns 201 with the correct shape."""
    payload = {
        "site_id": str(test_site.id),
        "plan_name": "starter",
        "monthly_fee_cents": 9900,
        "max_devices": 3,
        **_future_dates(),
    }
    response = await client.post("/licenses/", json=payload, headers=portal_auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["site_id"] == str(test_site.id)
    assert body["plan_name"] == "starter"
    assert body["status"] == "active"
    assert body["monthly_fee_cents"] == 9900
    assert body["max_devices"] == 3


async def test_list_licenses_returns_200(client, portal_auth_headers, test_license):
    """GET /licenses returns 200 with a list containing the seeded license."""
    response = await client.get("/licenses/", headers=portal_auth_headers)

    assert response.status_code == 200
    ids = [l["id"] for l in response.json()]
    assert str(test_license.id) in ids


async def test_get_license_returns_correct_license(client, portal_auth_headers, test_license):
    """GET /licenses/{id} returns the correct license."""
    response = await client.get(f"/licenses/{test_license.id}", headers=portal_auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(test_license.id)


async def test_update_license_plan_name(client, portal_auth_headers, test_license):
    """PATCH /licenses/{id} updates the plan name."""
    response = await client.patch(
        f"/licenses/{test_license.id}",
        json={"plan_name": "pro"},
        headers=portal_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["plan_name"] == "pro"


async def test_update_license_max_devices(client, portal_auth_headers, test_license):
    """PATCH /licenses/{id} updates the seat capacity."""
    response = await client.patch(
        f"/licenses/{test_license.id}",
        json={"max_devices": 5},
        headers=portal_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["max_devices"] == 5


async def test_disable_and_enable_license(client, portal_auth_headers, test_license):
    """POST /licenses/{id}/disable then /enable toggles status correctly."""
    r1 = await client.post(f"/licenses/{test_license.id}/disable", headers=portal_auth_headers)
    assert r1.status_code == 200
    assert r1.json()["status"] == "disabled"

    r2 = await client.post(f"/licenses/{test_license.id}/enable", headers=portal_auth_headers)
    assert r2.status_code == 200
    assert r2.json()["status"] == "active"


# ── Auth failure ──────────────────────────────────────────────────────────────


async def test_list_licenses_no_token_returns_403(client):
    """GET /licenses without a token returns 403."""
    response = await client.get("/licenses/")
    assert response.status_code == 403


async def test_create_license_no_token_returns_403(client, test_site):
    """POST /licenses without a token returns 403."""
    payload = {"site_id": str(test_site.id), "plan_name": "starter", "monthly_fee_cents": 0, "max_devices": 1, **_future_dates()}
    response = await client.post("/licenses/", json=payload)
    assert response.status_code == 403


# ── Invalid input ─────────────────────────────────────────────────────────────


async def test_create_license_missing_site_id_returns_422(client, portal_auth_headers):
    """POST /licenses without site_id returns 422."""
    payload = {"plan_name": "starter", "monthly_fee_cents": 9900, "max_devices": 1, **_future_dates()}
    response = await client.post("/licenses/", json=payload, headers=portal_auth_headers)
    assert response.status_code == 422


async def test_create_license_missing_plan_name_returns_422(client, portal_auth_headers, test_site):
    """POST /licenses without plan_name returns 422."""
    payload = {"site_id": str(test_site.id), "monthly_fee_cents": 9900, "max_devices": 1, **_future_dates()}
    response = await client.post("/licenses/", json=payload, headers=portal_auth_headers)
    assert response.status_code == 422


async def test_create_license_missing_max_devices_returns_422(client, portal_auth_headers, test_site):
    """POST /licenses without max_devices returns 422."""
    payload = {"site_id": str(test_site.id), "plan_name": "starter", "monthly_fee_cents": 9900, **_future_dates()}
    response = await client.post("/licenses/", json=payload, headers=portal_auth_headers)
    assert response.status_code == 422


async def test_create_license_zero_max_devices_returns_422(client, portal_auth_headers, test_site):
    """POST /licenses with max_devices=0 returns 422 — at least one seat is required."""
    payload = {
        "site_id": str(test_site.id),
        "plan_name": "starter",
        "monthly_fee_cents": 9900,
        "max_devices": 0,
        **_future_dates(),
    }
    response = await client.post("/licenses/", json=payload, headers=portal_auth_headers)
    assert response.status_code == 422


async def test_create_license_expires_before_starts_returns_422(client, portal_auth_headers, test_site):
    """POST /licenses where expires_at <= starts_at returns 422."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "site_id": str(test_site.id),
        "plan_name": "starter",
        "monthly_fee_cents": 0,
        "max_devices": 1,
        "starts_at": now.isoformat(),
        "expires_at": (now - timedelta(days=1)).isoformat(),
    }
    response = await client.post("/licenses/", json=payload, headers=portal_auth_headers)
    assert response.status_code == 422


# ── Business rule violations ──────────────────────────────────────────────────


async def test_create_license_unknown_site_returns_404(client, portal_auth_headers):
    """POST /licenses with a non-existent site_id returns 404."""
    payload = {"site_id": str(uuid.uuid4()), "plan_name": "starter", "monthly_fee_cents": 0, "max_devices": 1, **_future_dates()}
    response = await client.post("/licenses/", json=payload, headers=portal_auth_headers)
    assert response.status_code == 404


async def test_create_duplicate_license_returns_409(client, portal_auth_headers, test_site, test_license):
    """POST /licenses for a site that already has a license returns 409."""
    payload = {"site_id": str(test_site.id), "plan_name": "pro", "monthly_fee_cents": 0, "max_devices": 1, **_future_dates()}
    response = await client.post("/licenses/", json=payload, headers=portal_auth_headers)
    assert response.status_code == 409


async def test_get_unknown_license_returns_404(client, portal_auth_headers):
    """GET /licenses/{unknown_id} returns 404."""
    response = await client.get(f"/licenses/{uuid.uuid4()}", headers=portal_auth_headers)
    assert response.status_code == 404


async def test_disable_already_disabled_license_returns_409(client, portal_auth_headers, test_license):
    """Disabling an already-disabled license returns 409."""
    await client.post(f"/licenses/{test_license.id}/disable", headers=portal_auth_headers)
    response = await client.post(f"/licenses/{test_license.id}/disable", headers=portal_auth_headers)
    assert response.status_code == 409


async def test_enable_active_license_returns_409(client, portal_auth_headers, test_license):
    """Enabling an active (non-disabled) license returns 409."""
    response = await client.post(f"/licenses/{test_license.id}/enable", headers=portal_auth_headers)
    assert response.status_code == 409


# ── Audit log assertions ──────────────────────────────────────────────────────


async def test_create_license_writes_audit_log(client, db, portal_auth_headers, test_site):
    """POST /licenses writes a LICENSE_CREATED audit row."""
    payload = {
        "site_id": str(test_site.id),
        "plan_name": "audit-plan",
        "monthly_fee_cents": 4900,
        "max_devices": 1,
        **_future_dates(),
    }
    response = await client.post("/licenses/", json=payload, headers=portal_auth_headers)
    license_id = response.json()["id"]

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == license_id,
            AuditLog.action == LICENSE_CREATED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["plan_name"] == "audit-plan"


async def test_update_license_writes_audit_log(client, db, portal_auth_headers, test_license):
    """PATCH /licenses/{id} writes a LICENSE_UPDATED audit row."""
    await client.patch(
        f"/licenses/{test_license.id}",
        json={"plan_name": "enterprise"},
        headers=portal_auth_headers,
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_license.id),
            AuditLog.action == LICENSE_UPDATED,
        )
    )
    row = result.scalar_one()
    assert row.before_state["plan_name"] == "starter"
    assert row.after_state["plan_name"] == "enterprise"


async def test_disable_license_writes_audit_log(client, db, portal_auth_headers, test_license):
    """POST /licenses/{id}/disable writes a LICENSE_DISABLED audit row."""
    await client.post(f"/licenses/{test_license.id}/disable", headers=portal_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_license.id),
            AuditLog.action == LICENSE_DISABLED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["status"] == "disabled"


async def test_enable_license_writes_audit_log(client, db, portal_auth_headers, test_license):
    """POST /licenses/{id}/enable writes a LICENSE_ENABLED audit row."""
    await client.post(f"/licenses/{test_license.id}/disable", headers=portal_auth_headers)
    await client.post(f"/licenses/{test_license.id}/enable", headers=portal_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_license.id),
            AuditLog.action == LICENSE_ENABLED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["status"] == "active"


# ── GET /licenses/management (scoped list) ─────────────────────────────────────


async def test_list_licenses_management_without_permission_returns_403(
    client, mgmt_auth_headers, test_license
):
    """A management caller whose access profile lacks 'license_billing' is denied."""
    response = await client.get("/licenses/management", headers=mgmt_auth_headers)
    assert response.status_code == 403


async def test_list_licenses_management_with_permission_returns_200(
    client, db, mgmt_auth_headers, test_manager_profile, test_license
):
    """A management caller granted 'license_billing' sees licenses in their brand."""
    db.add(
        AccessProfilePagePermission(
            id=uuid.uuid4(), access_profile_id=test_manager_profile.id, page_key="license_billing"
        )
    )
    await db.commit()

    response = await client.get("/licenses/management", headers=mgmt_auth_headers)

    assert response.status_code == 200
    ids = [l["id"] for l in response.json()]
    assert str(test_license.id) in ids


async def test_list_licenses_management_no_token_returns_403(client):
    """GET /licenses/management without a token returns 403."""
    response = await client.get("/licenses/management")
    assert response.status_code == 403


async def test_list_licenses_management_excludes_other_brands(
    client, db, mgmt_auth_headers, test_manager_profile, test_group
):
    """A brand/site-scope caller never sees a license belonging to a different brand."""
    db.add(
        AccessProfilePagePermission(
            id=uuid.uuid4(), access_profile_id=test_manager_profile.id, page_key="license_billing"
        )
    )

    other_brand = Brand(
        id=uuid.uuid4(),
        group_id=test_group.id,
        name="Other Brand",
        is_active=True,
        timezone="Australia/Sydney",
        currency="AUD",
        country="AU",
    )
    db.add(other_brand)
    await db.flush()

    other_site = Site(
        id=uuid.uuid4(),
        brand_id=other_brand.id,
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
    await db.commit()

    response = await client.get("/licenses/management", headers=mgmt_auth_headers)

    assert response.status_code == 200
    ids = [l["id"] for l in response.json()]
    assert str(other_license.id) not in ids


# ── PATCH /licenses/management/{id} (seat capacity only) ───────────────────────


async def test_update_license_management_without_permission_returns_403(
    client, mgmt_auth_headers, test_license
):
    """A management caller lacking 'license_billing' cannot edit seat capacity."""
    response = await client.patch(
        f"/licenses/management/{test_license.id}", json={"max_devices": 5}, headers=mgmt_auth_headers
    )
    assert response.status_code == 403


async def test_update_license_management_with_permission_succeeds(
    client, db, mgmt_auth_headers, test_manager_profile, test_license
):
    """A management caller granted 'license_billing' can update seat capacity."""
    db.add(
        AccessProfilePagePermission(
            id=uuid.uuid4(), access_profile_id=test_manager_profile.id, page_key="license_billing"
        )
    )
    await db.commit()

    response = await client.patch(
        f"/licenses/management/{test_license.id}", json={"max_devices": 5}, headers=mgmt_auth_headers
    )

    assert response.status_code == 200
    assert response.json()["max_devices"] == 5


async def test_update_license_management_cannot_change_commercial_terms(
    client, db, mgmt_auth_headers, test_manager_profile, test_license
):
    """The management schema has no plan_name/monthly_fee_cents/expires_at field to change them with."""
    db.add(
        AccessProfilePagePermission(
            id=uuid.uuid4(), access_profile_id=test_manager_profile.id, page_key="license_billing"
        )
    )
    await db.commit()

    response = await client.patch(
        f"/licenses/management/{test_license.id}",
        json={"max_devices": 5, "plan_name": "enterprise", "monthly_fee_cents": 999999},
        headers=mgmt_auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["max_devices"] == 5
    assert body["plan_name"] == test_license.plan_name
    assert body["monthly_fee_cents"] == test_license.monthly_fee_cents


async def test_update_license_management_writes_audit_log(
    client, db, mgmt_auth_headers, test_manager_profile, test_license
):
    """A successful management seat-capacity update writes a LICENSE_UPDATED row attributed to the caller."""
    db.add(
        AccessProfilePagePermission(
            id=uuid.uuid4(), access_profile_id=test_manager_profile.id, page_key="license_billing"
        )
    )
    await db.commit()

    await client.patch(
        f"/licenses/management/{test_license.id}", json={"max_devices": 5}, headers=mgmt_auth_headers
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_license.id),
            AuditLog.action == LICENSE_UPDATED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["max_devices"] == 5


async def test_update_license_management_pos_access_forbidden(client, pos_auth_headers, test_license):
    """A raw POS terminal session can never edit a license."""
    response = await client.patch(
        f"/licenses/management/{test_license.id}", json={"max_devices": 5}, headers=pos_auth_headers
    )
    assert response.status_code == 403


async def test_update_license_management_portal_admin_always_permitted(
    client, portal_auth_headers, test_license
):
    """A portal admin (superadmin) may edit any license via the management route too."""
    response = await client.patch(
        f"/licenses/management/{test_license.id}", json={"max_devices": 5}, headers=portal_auth_headers
    )
    assert response.status_code == 200
    assert response.json()["max_devices"] == 5
