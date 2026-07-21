"""Integration tests for /sites routes.

Covers all five required scenarios per tests_CLAUDE.md:
1. Happy path — correct response shape
2. Auth failure — no token → 403
3. Invalid input — missing fields → 422
4. Business rule — 404 for unknown site/brand, 409 for duplicate state change
5. Audit log — every write asserts the correct audit_logs row
"""

import io
import uuid
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.constants.audit_actions import (
    SITE_ACTIVATED,
    SITE_CREATED,
    SITE_LOGO_UPDATED,
    SITE_SUSPENDED,
    SITE_UPDATED,
)
from app.models.audit_log import AuditLog
from app.models.brand import Brand
from app.models.group import Group
from app.models.site import Site
from app.models.user import User
from app.utils.security import create_mgmt_access_token

# Patch target for upload_logo tests so no real Supabase call goes out
_UPLOAD_IMAGE_PATH = "app.services.site_service.upload_image"
# Patch target for request-billing-info tests so no real Resend call goes out
_SEND_BILLING_EMAIL_PATH = "app.services.branding_service.send_billing_info_request_email"

# Master-user credentials required on every POST /sites/ since Change 1
_MASTER_CREDS = {"master_email": "owner@sitetest.example", "master_password": "TestPass123!"}


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_create_site_returns_201(client, portal_auth_headers, test_brand):
    """POST /sites creates a site and returns 201 with the correct shape."""
    response = await client.post(
        "/sites/",
        json={"brand_id": str(test_brand.id), "name": "Sydney CBD", **_MASTER_CREDS},
        headers=portal_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Sydney CBD"
    assert body["brand_id"] == str(test_brand.id)
    assert body["is_active"] is True


async def test_list_sites_returns_200(client, portal_auth_headers, test_site):
    """GET /sites returns 200 with a list containing the seeded site."""
    response = await client.get("/sites/", headers=portal_auth_headers)

    assert response.status_code == 200
    ids = [s["id"] for s in response.json()]
    assert str(test_site.id) in ids


async def test_get_site_returns_correct_site(client, portal_auth_headers, test_site):
    """GET /sites/{id} returns the correct site."""
    response = await client.get(f"/sites/{test_site.id}", headers=portal_auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(test_site.id)


async def test_update_site_name(client, portal_auth_headers, test_site):
    """PATCH /sites/{id} updates the site name."""
    response = await client.patch(
        f"/sites/{test_site.id}", json={"name": "Melbourne CBD"}, headers=portal_auth_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Melbourne CBD"


async def test_suspend_and_activate_site(client, portal_auth_headers, test_site):
    """POST /sites/{id}/suspend then /activate toggles is_active correctly."""
    r1 = await client.post(f"/sites/{test_site.id}/suspend", headers=portal_auth_headers)
    assert r1.status_code == 200
    assert r1.json()["is_active"] is False

    r2 = await client.post(f"/sites/{test_site.id}/activate", headers=portal_auth_headers)
    assert r2.status_code == 200
    assert r2.json()["is_active"] is True


# ── Auth failure ──────────────────────────────────────────────────────────────


async def test_list_sites_no_token_returns_403(client):
    """GET /sites without a token returns 403."""
    response = await client.get("/sites/")
    assert response.status_code == 403


async def test_create_site_no_token_returns_403(client, test_brand):
    """POST /sites without a token returns 403."""
    response = await client.post(
        "/sites/", json={"brand_id": str(test_brand.id), "name": "Test"}
    )
    assert response.status_code == 403


# ── Invalid input ─────────────────────────────────────────────────────────────


async def test_create_site_missing_name_returns_422(client, portal_auth_headers, test_brand):
    """POST /sites with no name returns 422."""
    response = await client.post(
        "/sites/", json={"brand_id": str(test_brand.id)}, headers=portal_auth_headers
    )
    assert response.status_code == 422


async def test_create_site_missing_brand_id_returns_422(client, portal_auth_headers):
    """POST /sites with no brand_id returns 422."""
    response = await client.post(
        "/sites/", json={"name": "No Brand"}, headers=portal_auth_headers
    )
    assert response.status_code == 422


# ── Business rule violations ──────────────────────────────────────────────────


async def test_create_site_unknown_brand_returns_404(client, portal_auth_headers):
    """POST /sites with a non-existent brand_id returns 404."""
    response = await client.post(
        "/sites/",
        json={"brand_id": str(uuid.uuid4()), "name": "Orphan Site", **_MASTER_CREDS},
        headers=portal_auth_headers,
    )
    assert response.status_code == 404


async def test_get_unknown_site_returns_404(client, portal_auth_headers):
    """GET /sites/{unknown_id} returns 404."""
    response = await client.get(f"/sites/{uuid.uuid4()}", headers=portal_auth_headers)
    assert response.status_code == 404


async def test_suspend_already_suspended_site_returns_409(client, portal_auth_headers, test_site):
    """Suspending an already-suspended site returns 409."""
    await client.post(f"/sites/{test_site.id}/suspend", headers=portal_auth_headers)
    response = await client.post(f"/sites/{test_site.id}/suspend", headers=portal_auth_headers)
    assert response.status_code == 409


# ── Audit log assertions ──────────────────────────────────────────────────────


async def test_create_site_writes_audit_log(client, db, portal_auth_headers, test_brand):
    """POST /sites writes a SITE_CREATED audit row."""
    response = await client.post(
        "/sites/",
        json={"brand_id": str(test_brand.id), "name": "Audit Site", **_MASTER_CREDS},
        headers=portal_auth_headers,
    )
    site_id = response.json()["id"]

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == site_id,
            AuditLog.action == SITE_CREATED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["name"] == "Audit Site"


async def test_update_site_writes_audit_log(client, db, portal_auth_headers, test_site):
    """PATCH /sites/{id} writes a SITE_UPDATED audit row with before/after."""
    await client.patch(
        f"/sites/{test_site.id}", json={"name": "New Name"}, headers=portal_auth_headers
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_site.id),
            AuditLog.action == SITE_UPDATED,
        )
    )
    row = result.scalar_one()
    assert row.before_state["name"] == "Test Site"
    assert row.after_state["name"] == "New Name"


async def test_suspend_site_writes_audit_log(client, db, portal_auth_headers, test_site):
    """POST /sites/{id}/suspend writes a SITE_SUSPENDED audit row."""
    await client.post(f"/sites/{test_site.id}/suspend", headers=portal_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_site.id),
            AuditLog.action == SITE_SUSPENDED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["is_active"] is False


# ── Master User auto-creation ───────────────────────────────────────────────────


async def test_create_site_master_user_has_group_id(client, db, portal_auth_headers, test_brand, test_group):
    """POST /sites's auto-created Master User has group_id resolved via its brand."""
    response = await client.post(
        "/sites/",
        json={"brand_id": str(test_brand.id), "name": "Group Id Test Site", **_MASTER_CREDS},
        headers=portal_auth_headers,
    )
    site_id = response.json()["id"]

    result = await db.execute(
        select(User).where(
            User.brand_id == test_brand.id,
            User.is_master_user == True,  # noqa: E712
            User.name == "Group Id Test Site",
        )
    )
    master_user = result.scalar_one()
    assert master_user.group_id == test_group.id
    assert str(site_id)  # site created successfully alongside the master user


# ── Company profile fields ──────────────────────────────────────────────────


async def test_create_site_with_profile_fields(client, portal_auth_headers, test_brand):
    """POST /sites accepts and returns the full company-profile field set, including address."""
    response = await client.post(
        "/sites/",
        json={
            "brand_id": str(test_brand.id),
            "name": "Profile Fields Site",
            "timezone": "America/New_York",
            "currency": "USD",
            "country": "US",
            "tax_id_value": "12-3456789",
            "billing_email": "billing@example.com",
            "address_street": "123 Main St",
            "address_state": "NY",
            "address_postcode": "10001",
            **_MASTER_CREDS,
        },
        headers=portal_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["timezone"] == "America/New_York"
    assert body["currency"] == "USD"
    assert body["country"] == "US"
    assert body["tax_id_value"] == "12-3456789"
    assert body["billing_email"] == "billing@example.com"
    assert body["address_street"] == "123 Main St"
    assert body["address_state"] == "NY"
    assert body["address_postcode"] == "10001"


async def test_update_site_currency_writes_before_after_audit(client, db, portal_auth_headers, test_site):
    """PATCH /sites/{id} changing currency records the old and new value in the audit row."""
    response = await client.patch(
        f"/sites/{test_site.id}", json={"currency": "NZD"}, headers=portal_auth_headers
    )
    assert response.status_code == 200
    assert response.json()["currency"] == "NZD"

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_site.id),
            AuditLog.action == SITE_UPDATED,
        )
    )
    row = result.scalar_one()
    assert row.before_state["currency"] == "AUD"
    assert row.after_state["currency"] == "NZD"


# ── Logo upload ──────────────────────────────────────────────────────────────


async def test_upload_site_logo_returns_200(client, portal_auth_headers, test_site):
    """POST /sites/{id}/logo accepts a valid image and returns the updated site."""
    with patch(_UPLOAD_IMAGE_PATH, new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = "https://example.test/logos/site.jpg"
        response = await client.post(
            f"/sites/{test_site.id}/logo",
            files={"file": ("logo.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
            headers=portal_auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["logo_url"] == "https://example.test/logos/site.jpg"


async def test_upload_site_logo_writes_audit_log(client, db, portal_auth_headers, test_site):
    """POST /sites/{id}/logo writes a SITE_LOGO_UPDATED audit row."""
    with patch(_UPLOAD_IMAGE_PATH, new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = "https://example.test/logos/site.jpg"
        await client.post(
            f"/sites/{test_site.id}/logo",
            files={"file": ("logo.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
            headers=portal_auth_headers,
        )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_site.id),
            AuditLog.action == SITE_LOGO_UPDATED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["logo_url"] == "https://example.test/logos/site.jpg"


async def test_upload_site_logo_rejects_oversized_file(client, portal_auth_headers, test_site):
    """POST /sites/{id}/logo with a file over 1 MB returns 413."""
    oversized = b"x" * (1024 * 1024 + 1)
    response = await client.post(
        f"/sites/{test_site.id}/logo",
        files={"file": ("logo.jpg", io.BytesIO(oversized), "image/jpeg")},
        headers=portal_auth_headers,
    )
    assert response.status_code == 413


async def test_upload_site_logo_rejects_invalid_content_type(client, portal_auth_headers, test_site):
    """POST /sites/{id}/logo with a non-image content type returns 415."""
    response = await client.post(
        f"/sites/{test_site.id}/logo",
        files={"file": ("notes.txt", io.BytesIO(b"not an image"), "text/plain")},
        headers=portal_auth_headers,
    )
    assert response.status_code == 415


# ── Request billing info ─────────────────────────────────────────────────────


async def test_request_site_billing_info_inherits_from_brand(
    client, db, portal_auth_headers, test_site, test_brand, test_billing_info_template
):
    """POST /sites/{id}/request-billing-info falls back to the parent brand's billing_email."""
    test_brand.billing_email = "billing@brand.test"
    await db.commit()

    with patch(_SEND_BILLING_EMAIL_PATH, new_callable=AsyncMock) as mock_send:
        response = await client.post(
            f"/sites/{test_site.id}/request-billing-info", headers=portal_auth_headers
        )

    assert response.status_code == 200
    body = response.json()
    assert body["sent_to"] == "billing@brand.test"
    assert body["source_level"] == "brand"
    mock_send.assert_awaited_once()


async def test_request_site_billing_info_no_email_returns_409(
    client, portal_auth_headers, test_site, test_billing_info_template
):
    """POST /sites/{id}/request-billing-info with no billing_email anywhere in the chain returns 409."""
    response = await client.post(
        f"/sites/{test_site.id}/request-billing-info", headers=portal_auth_headers
    )
    assert response.status_code == 409


async def test_request_site_billing_info_writes_audit_log(
    client, db, portal_auth_headers, test_site, test_billing_info_template
):
    """POST /sites/{id}/request-billing-info writes a BILLING_INFO_REQUESTED audit row."""
    from app.constants.audit_actions import BILLING_INFO_REQUESTED

    test_site.billing_email = "billing@site.test"
    await db.commit()

    with patch(_SEND_BILLING_EMAIL_PATH, new_callable=AsyncMock):
        await client.post(f"/sites/{test_site.id}/request-billing-info", headers=portal_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_site.id),
            AuditLog.action == BILLING_INFO_REQUESTED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["sent_to"] == "billing@site.test"


# ── Management portal access (tenant-facing Company Profile page) ────────────


async def test_get_site_by_own_site_scope_returns_200(client, mgmt_auth_headers, test_site):
    """A Site-scoped management caller can read their own Site's profile."""
    response = await client.get(f"/sites/{test_site.id}", headers=mgmt_auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(test_site.id)


async def test_update_site_by_own_site_scope_returns_200(client, mgmt_auth_headers, test_site):
    """A Site-scoped management caller can edit their own Site's profile."""
    response = await client.patch(
        f"/sites/{test_site.id}", json={"name": "Updated By Management"}, headers=mgmt_auth_headers
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated By Management"


async def test_update_site_by_own_site_scope_writes_audit_log_with_mgmt_actor(
    client, db, mgmt_auth_headers, test_site, test_user
):
    """PATCH /sites/{id} by a management caller attributes the audit row to that user."""
    await client.patch(
        f"/sites/{test_site.id}", json={"name": "Mgmt Audit Name"}, headers=mgmt_auth_headers
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_site.id),
            AuditLog.action == SITE_UPDATED,
        )
    )
    row = result.scalar_one()
    assert row.actor_id == test_user.id
    assert row.after_state["name"] == "Mgmt Audit Name"


async def test_get_site_by_ancestor_brand_scope_returns_404(client, test_site, test_brand_grant, test_user):
    """A Brand-scoped management caller cannot read a descendant Site's profile — Site is the leaf
    scope in the Company Profile page and has no ancestor-read allowance (unlike Group/Brand)."""
    token = create_mgmt_access_token(
        user_id=str(test_user.id),
        scope="brand",
        grant_id=str(test_brand_grant.id),
        site_id=None,
        brand_id=str(test_brand_grant.brand_id),
        group_id=None,
    )
    response = await client.get(
        f"/sites/{test_site.id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


async def test_get_site_unrelated_scope_returns_404(client, mgmt_auth_headers, db):
    """A management caller cannot read a Site outside their own scope."""
    other_group = Group(
        id=uuid.uuid4(), name="Other Group", is_active=True, timezone="Australia/Sydney", currency="AUD", country="AU"
    )
    db.add(other_group)
    await db.flush()
    other_brand = Brand(
        id=uuid.uuid4(),
        group_id=other_group.id,
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
        address_street="1 Other Street",
        address_state="NSW",
        address_postcode="2000",
    )
    db.add(other_site)
    await db.commit()

    response = await client.get(f"/sites/{other_site.id}", headers=mgmt_auth_headers)
    assert response.status_code == 404
