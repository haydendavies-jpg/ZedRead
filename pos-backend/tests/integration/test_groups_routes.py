"""Integration tests for /groups routes.

Covers all five required scenarios per tests_CLAUDE.md:
1. Happy path — correct response shape, correct status codes
2. Auth failure — no token → 403, (all routes require auth)
3. Invalid input — missing required fields → 422
4. Business rule — 404 for unknown group, 409 for duplicate state change
5. Audit log — every write asserts the correct audit_logs row
"""

import uuid

from sqlalchemy import select

from app.constants.audit_actions import GROUP_ACTIVATED, GROUP_CREATED, GROUP_SUSPENDED, GROUP_UPDATED
from app.models.audit_log import AuditLog
from app.models.group import Group


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_create_group_returns_201(client, portal_auth_headers):
    """POST /groups creates a group and returns 201 with the correct shape."""
    response = await client.post(
        "/groups/", json={"name": "Acme Corp"}, headers=portal_auth_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme Corp"
    assert body["is_active"] is True
    assert "id" in body


async def test_list_groups_returns_200(client, portal_auth_headers, test_group):
    """GET /groups returns 200 with a list containing the seeded group."""
    response = await client.get("/groups/", headers=portal_auth_headers)

    assert response.status_code == 200
    ids = [g["id"] for g in response.json()]
    assert str(test_group.id) in ids


async def test_get_group_returns_correct_group(client, portal_auth_headers, test_group):
    """GET /groups/{id} returns the correct group."""
    response = await client.get(f"/groups/{test_group.id}", headers=portal_auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(test_group.id)


async def test_update_group_name(client, portal_auth_headers, test_group):
    """PATCH /groups/{id} updates the name and returns the updated group."""
    response = await client.patch(
        f"/groups/{test_group.id}", json={"name": "Updated Name"}, headers=portal_auth_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"


async def test_suspend_and_activate_group(client, portal_auth_headers, test_group):
    """POST /groups/{id}/suspend then /activate toggles is_active correctly."""
    r1 = await client.post(f"/groups/{test_group.id}/suspend", headers=portal_auth_headers)
    assert r1.status_code == 200
    assert r1.json()["is_active"] is False

    r2 = await client.post(f"/groups/{test_group.id}/activate", headers=portal_auth_headers)
    assert r2.status_code == 200
    assert r2.json()["is_active"] is True


# ── Auth failure ──────────────────────────────────────────────────────────────


async def test_list_groups_no_token_returns_403(client):
    """GET /groups without a token returns 403."""
    response = await client.get("/groups/")
    assert response.status_code == 403


async def test_create_group_no_token_returns_403(client):
    """POST /groups without a token returns 403."""
    response = await client.post("/groups/", json={"name": "Test"})
    assert response.status_code == 403


# ── Invalid input ─────────────────────────────────────────────────────────────


async def test_create_group_missing_name_returns_422(client, portal_auth_headers):
    """POST /groups with no name returns 422."""
    response = await client.post("/groups/", json={}, headers=portal_auth_headers)
    assert response.status_code == 422


async def test_create_group_empty_name_returns_422(client, portal_auth_headers):
    """POST /groups with empty string name returns 422 (min_length=1)."""
    response = await client.post("/groups/", json={"name": ""}, headers=portal_auth_headers)
    assert response.status_code == 422


# ── Business rule violations ──────────────────────────────────────────────────


async def test_get_unknown_group_returns_404(client, portal_auth_headers):
    """GET /groups/{unknown_id} returns 404."""
    response = await client.get(f"/groups/{uuid.uuid4()}", headers=portal_auth_headers)
    assert response.status_code == 404


async def test_suspend_already_suspended_group_returns_409(client, portal_auth_headers, test_group):
    """Suspending an already-suspended group returns 409 Conflict."""
    await client.post(f"/groups/{test_group.id}/suspend", headers=portal_auth_headers)
    response = await client.post(f"/groups/{test_group.id}/suspend", headers=portal_auth_headers)
    assert response.status_code == 409


async def test_activate_already_active_group_returns_409(client, portal_auth_headers, test_group):
    """Activating an already-active group returns 409 Conflict."""
    response = await client.post(f"/groups/{test_group.id}/activate", headers=portal_auth_headers)
    assert response.status_code == 409


# ── Audit log assertions ──────────────────────────────────────────────────────


async def test_create_group_writes_audit_log(client, db, portal_auth_headers):
    """POST /groups writes a GROUP_CREATED audit row with correct fields."""
    response = await client.post(
        "/groups/", json={"name": "Audit Test Group"}, headers=portal_auth_headers
    )
    group_id = response.json()["id"]

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == group_id,
            AuditLog.action == GROUP_CREATED,
        )
    )
    row = result.scalar_one()
    assert row.entity_type == "group"
    assert row.after_state["name"] == "Audit Test Group"


async def test_update_group_writes_audit_log(client, db, portal_auth_headers, test_group):
    """PATCH /groups/{id} writes a GROUP_UPDATED audit row with before/after state."""
    await client.patch(
        f"/groups/{test_group.id}", json={"name": "New Name"}, headers=portal_auth_headers
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_group.id),
            AuditLog.action == GROUP_UPDATED,
        )
    )
    row = result.scalar_one()
    assert row.before_state["name"] == "Test Group"
    assert row.after_state["name"] == "New Name"


async def test_suspend_group_writes_audit_log(client, db, portal_auth_headers, test_group):
    """POST /groups/{id}/suspend writes a GROUP_SUSPENDED audit row."""
    await client.post(f"/groups/{test_group.id}/suspend", headers=portal_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_group.id),
            AuditLog.action == GROUP_SUSPENDED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["is_active"] is False


async def test_activate_group_writes_audit_log(client, db, portal_auth_headers, test_group):
    """POST /groups/{id}/activate writes a GROUP_ACTIVATED audit row."""
    # First suspend so activation is valid
    await client.post(f"/groups/{test_group.id}/suspend", headers=portal_auth_headers)
    await client.post(f"/groups/{test_group.id}/activate", headers=portal_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_group.id),
            AuditLog.action == GROUP_ACTIVATED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["is_active"] is True
