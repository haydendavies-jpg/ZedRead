"""Integration tests for category routes, including the Stage 16 reporting group requirement.

Covers:
1. Happy path — create (with and without explicit reporting_group_id)/list/update a category
2. Auth failure — no token returns 403; POS token returns 403 on writes
3. Invalid input — missing required fields return 422
4. Business rules — cross-brand reporting_group_id returns 400; system category rename returns 403
5. Audit log — CATEGORY_CREATED, CATEGORY_UPDATED written
"""

import uuid

import pytest
from sqlalchemy import select

from app.constants.audit_actions import CATEGORY_CREATED, CATEGORY_UPDATED
from app.models.audit_log import AuditLog
from app.models.reporting_group import ReportingGroup

pytestmark = pytest.mark.asyncio


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_create_category_without_reporting_group_uses_brand_default(
    client, mgmt_auth_headers, test_brand, test_reporting_group
):
    """POST /categories without reporting_group_id auto-assigns the brand's default."""
    response = await client.post(
        "/categories",
        json={"name": "Mains", "brand_id": str(test_brand.id)},
        headers=mgmt_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Mains"
    assert body["reporting_group_id"] == str(test_reporting_group.id)


async def test_create_category_with_explicit_reporting_group(
    client, mgmt_auth_headers, test_brand, test_reporting_group
):
    """POST /categories with an explicit reporting_group_id uses it."""
    create_resp = await client.post(
        "/reporting-groups", json={"name": "Drinks"}, headers=mgmt_auth_headers
    )
    group_id = create_resp.json()["id"]

    response = await client.post(
        "/categories",
        json={"name": "Beverages", "brand_id": str(test_brand.id), "reporting_group_id": group_id},
        headers=mgmt_auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["reporting_group_id"] == group_id


async def test_create_category_writes_audit_log(client, db, mgmt_auth_headers, test_user, test_brand, test_reporting_group):
    """Creating a category writes a CATEGORY_CREATED audit row."""
    await client.post(
        "/categories",
        json={"name": "Desserts", "brand_id": str(test_brand.id)},
        headers=mgmt_auth_headers,
    )

    result = await db.execute(select(AuditLog).where(AuditLog.action == CATEGORY_CREATED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_update_category_reporting_group_writes_audit_log(
    client, db, mgmt_auth_headers, test_user, test_brand, test_reporting_group
):
    """Updating a category's reporting group writes a CATEGORY_UPDATED audit row."""
    create_resp = await client.post(
        "/categories",
        json={"name": "Sides", "brand_id": str(test_brand.id)},
        headers=mgmt_auth_headers,
    )
    category_id = create_resp.json()["id"]

    group_resp = await client.post(
        "/reporting-groups", json={"name": "Other Group"}, headers=mgmt_auth_headers
    )
    new_group_id = group_resp.json()["id"]

    response = await client.patch(
        f"/categories/{category_id}",
        json={"reporting_group_id": new_group_id},
        headers=mgmt_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["reporting_group_id"] == new_group_id

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == CATEGORY_UPDATED, AuditLog.entity_id == category_id)
    )
    row = result.scalar_one()
    assert row.actor_id == test_user.id


# ── Stage 20 — include_inactive ──────────────────────────────────────────────


async def test_list_categories_excludes_inactive_by_default(
    client, db, mgmt_auth_headers, test_brand, test_reporting_group
):
    """GET /categories omits deactivated categories unless include_inactive=true."""
    create_resp = await client.post(
        "/categories",
        json={"name": "Seasonal", "brand_id": str(test_brand.id)},
        headers=mgmt_auth_headers,
    )
    category_id = create_resp.json()["id"]
    await client.patch(
        f"/categories/{category_id}", json={"is_active": False}, headers=mgmt_auth_headers
    )

    response = await client.get(
        "/categories", params={"brand_id": str(test_brand.id)}, headers=mgmt_auth_headers
    )

    assert response.status_code == 200
    ids = [c["id"] for c in response.json()]
    assert category_id not in ids


async def test_list_categories_include_inactive_returns_deactivated_row(
    client, db, mgmt_auth_headers, test_brand, test_reporting_group
):
    """GET /categories?include_inactive=true includes deactivated categories."""
    create_resp = await client.post(
        "/categories",
        json={"name": "Seasonal", "brand_id": str(test_brand.id)},
        headers=mgmt_auth_headers,
    )
    category_id = create_resp.json()["id"]
    await client.patch(
        f"/categories/{category_id}", json={"is_active": False}, headers=mgmt_auth_headers
    )

    response = await client.get(
        "/categories",
        params={"brand_id": str(test_brand.id), "include_inactive": "true"},
        headers=mgmt_auth_headers,
    )

    assert response.status_code == 200
    row = next(c for c in response.json() if c["id"] == category_id)
    assert row["is_active"] is False


# ── Auth failures ─────────────────────────────────────────────────────────────


async def test_create_category_no_token_returns_403(client, test_brand):
    """Creating a category without a token returns 403."""
    response = await client.post("/categories", json={"name": "Mains", "brand_id": str(test_brand.id)})
    assert response.status_code == 403


async def test_create_category_pos_token_returns_403(client, pos_auth_headers, test_brand):
    """Creating a category with a POS terminal token returns 403."""
    response = await client.post(
        "/categories",
        json={"name": "Mains", "brand_id": str(test_brand.id)},
        headers=pos_auth_headers,
    )
    assert response.status_code == 403


# ── Invalid input ─────────────────────────────────────────────────────────────


async def test_create_category_missing_name_returns_422(client, mgmt_auth_headers, test_brand):
    """Creating a category without a name returns 422."""
    response = await client.post(
        "/categories", json={"brand_id": str(test_brand.id)}, headers=mgmt_auth_headers
    )
    assert response.status_code == 422


# ── Business rules ────────────────────────────────────────────────────────────


async def test_create_category_cross_brand_reporting_group_returns_400(
    client, db, mgmt_auth_headers, test_brand, test_group
):
    """Assigning a category to a reporting group from a different brand returns 400."""
    from app.models.brand import Brand

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
    other_group = ReportingGroup(
        id=uuid.uuid4(), brand_id=other_brand.id, name="Other Default", is_default=True, is_system=True
    )
    db.add(other_group)
    await db.commit()

    response = await client.post(
        "/categories",
        json={
            "name": "Cross Brand Category",
            "brand_id": str(test_brand.id),
            "reporting_group_id": str(other_group.id),
        },
        headers=mgmt_auth_headers,
    )

    assert response.status_code == 400
    assert "brand" in response.json()["detail"].lower()


async def test_rename_system_category_returns_403(client, db, mgmt_auth_headers, test_brand, test_reporting_group):
    """A system category (e.g. the auto-seeded 'Uncategorised') cannot be renamed."""
    from app.models.category import Category

    system_cat = Category(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        reporting_group_id=test_reporting_group.id,
        name="Uncategorised",
        is_system=True,
        is_active=True,
    )
    db.add(system_cat)
    await db.commit()

    response = await client.patch(
        f"/categories/{system_cat.id}",
        json={"name": "Renamed"},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 403
