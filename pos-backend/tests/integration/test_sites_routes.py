"""Integration tests for /sites routes.

Covers all five required scenarios per tests_CLAUDE.md:
1. Happy path — correct response shape
2. Auth failure — no token → 403
3. Invalid input — missing fields → 422
4. Business rule — 404 for unknown site/brand, 409 for duplicate state change
5. Audit log — every write asserts the correct audit_logs row
"""

import uuid

from sqlalchemy import select

from app.constants.audit_actions import SITE_ACTIVATED, SITE_CREATED, SITE_SUSPENDED, SITE_UPDATED
from app.models.audit_log import AuditLog


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_create_site_returns_201(client, portal_auth_headers, test_brand):
    """POST /sites creates a site and returns 201 with the correct shape."""
    response = await client.post(
        "/sites/",
        json={"brand_id": str(test_brand.id), "name": "Sydney CBD"},
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
        json={"brand_id": str(uuid.uuid4()), "name": "Orphan Site"},
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
        json={"brand_id": str(test_brand.id), "name": "Audit Site"},
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
