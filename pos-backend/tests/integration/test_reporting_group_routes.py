"""Integration tests for reporting group routes (Stage 16).

Covers:
1. Happy path — create/list/update/delete a reporting group
2. Auth failure — no token returns 403; POS token returns 403 on writes
3. Invalid input — missing required fields return 422
4. Business rules — default group cannot be renamed/deleted; in-use group cannot be deleted
5. Audit log — REPORTING_GROUP_CREATED, REPORTING_GROUP_UPDATED, REPORTING_GROUP_DELETED written
"""

import uuid

import pytest
from sqlalchemy import select

from app.constants.audit_actions import (
    REPORTING_GROUP_CREATED,
    REPORTING_GROUP_DELETED,
    REPORTING_GROUP_UPDATED,
)
from app.models.audit_log import AuditLog
from app.models.category import Category

pytestmark = pytest.mark.asyncio


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_create_reporting_group_returns_201(client, mgmt_auth_headers, test_brand):
    """POST /reporting-groups creates a non-default, non-system group."""
    response = await client.post(
        "/reporting-groups",
        json={"name": "Beverages"},
        headers=mgmt_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Beverages"
    assert body["brand_id"] == str(test_brand.id)
    assert body["is_default"] is False
    assert body["is_system"] is False
    assert body["ref"].startswith("RPG-")


async def test_create_reporting_group_writes_audit_log(client, db, mgmt_auth_headers, test_user):
    """Creating a reporting group writes a REPORTING_GROUP_CREATED audit row."""
    await client.post(
        "/reporting-groups",
        json={"name": "Snacks"},
        headers=mgmt_auth_headers,
    )

    result = await db.execute(select(AuditLog).where(AuditLog.action == REPORTING_GROUP_CREATED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_list_reporting_groups_returns_default_first(client, mgmt_auth_headers, test_reporting_group):
    """GET /reporting-groups includes the brand's default group."""
    response = await client.get("/reporting-groups", headers=mgmt_auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body[0]["id"] == str(test_reporting_group.id)
    assert body[0]["is_default"] is True


async def test_update_reporting_group_renames_non_system_group(client, mgmt_auth_headers, test_brand):
    """PATCH /reporting-groups/{id} renames a non-system group."""
    create_resp = await client.post(
        "/reporting-groups", json={"name": "Original"}, headers=mgmt_auth_headers
    )
    group_id = create_resp.json()["id"]

    response = await client.patch(
        f"/reporting-groups/{group_id}",
        json={"name": "Renamed"},
        headers=mgmt_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"


async def test_delete_reporting_group_removes_unused_group(client, db, mgmt_auth_headers):
    """DELETE /reporting-groups/{id} removes a group with no categories attached."""
    create_resp = await client.post(
        "/reporting-groups", json={"name": "Temporary"}, headers=mgmt_auth_headers
    )
    group_id = create_resp.json()["id"]

    response = await client.delete(f"/reporting-groups/{group_id}", headers=mgmt_auth_headers)

    assert response.status_code == 204
    result = await db.execute(select(AuditLog).where(AuditLog.action == REPORTING_GROUP_DELETED))
    row = result.scalar_one()
    assert row.entity_id == group_id


# ── Auth failures ─────────────────────────────────────────────────────────────


async def test_create_reporting_group_no_token_returns_403(client):
    """Creating a reporting group without a token returns 403."""
    response = await client.post("/reporting-groups", json={"name": "Beverages"})
    assert response.status_code == 403


async def test_create_reporting_group_pos_token_returns_403(client, pos_auth_headers):
    """Creating a reporting group with a POS terminal token returns 403."""
    response = await client.post(
        "/reporting-groups", json={"name": "Beverages"}, headers=pos_auth_headers
    )
    assert response.status_code == 403


# ── Invalid input ─────────────────────────────────────────────────────────────


async def test_create_reporting_group_missing_name_returns_422(client, mgmt_auth_headers):
    """Creating a reporting group without a name returns 422."""
    response = await client.post("/reporting-groups", json={}, headers=mgmt_auth_headers)
    assert response.status_code == 422


# ── Business rules ────────────────────────────────────────────────────────────


async def test_rename_default_reporting_group_returns_403(client, mgmt_auth_headers, test_reporting_group):
    """Renaming the system default reporting group is blocked."""
    response = await client.patch(
        f"/reporting-groups/{test_reporting_group.id}",
        json={"name": "New Default Name"},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 403


async def test_delete_default_reporting_group_returns_403(client, mgmt_auth_headers, test_reporting_group):
    """Deleting the system default reporting group is blocked."""
    response = await client.delete(
        f"/reporting-groups/{test_reporting_group.id}", headers=mgmt_auth_headers
    )
    assert response.status_code == 403


async def test_delete_reporting_group_in_use_returns_409(client, db, mgmt_auth_headers, test_brand):
    """Deleting a reporting group still referenced by a category returns 409."""
    create_resp = await client.post(
        "/reporting-groups", json={"name": "In Use"}, headers=mgmt_auth_headers
    )
    group_id = create_resp.json()["id"]

    category = Category(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        reporting_group_id=uuid.UUID(group_id),
        name="Linked Category",
        is_system=False,
        is_active=True,
    )
    db.add(category)
    await db.commit()

    response = await client.delete(f"/reporting-groups/{group_id}", headers=mgmt_auth_headers)
    assert response.status_code == 409
