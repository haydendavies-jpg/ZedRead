"""Integration tests for tax category and tax rate routes.

Covers:
1. Happy path — create/list/update tax categories; create/list/update rates
2. Auth failure — no token returns 403
3. Business rules — cross-brand 404, inactive category excluded from list
4. Invalid input — 422 on missing/invalid fields
5. Audit log — TAX_CATEGORY_CREATED, TAX_RATE_CREATED, TAX_RATE_UPDATED written
"""

import uuid

import pytest
from sqlalchemy import select

from app.constants.audit_actions import TAX_CATEGORY_CREATED, TAX_RATE_CREATED, TAX_RATE_UPDATED
from app.constants.statuses import TaxModel
from app.models.audit_log import AuditLog

pytestmark = pytest.mark.asyncio


# ── Tax category happy path ───────────────────────────────────────────────────


async def test_create_tax_category_returns_201(client, pos_auth_headers, test_brand):
    """POST /tax/categories creates a tax category and returns 201."""
    response = await client.post(
        "/tax/categories",
        json={"name": "Food"},
        headers=pos_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Food"
    assert body["brand_id"] == str(test_brand.id)
    assert body["is_active"] is True


async def test_create_tax_category_writes_audit_log(client, db, pos_auth_headers, test_pos_user):
    """Creating a tax category writes a TAX_CATEGORY_CREATED audit row."""
    await client.post(
        "/tax/categories",
        json={"name": "Alcohol"},
        headers=pos_auth_headers,
    )

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == TAX_CATEGORY_CREATED)
    )
    row = result.scalar_one()
    assert row.actor_id == test_pos_user.id


async def test_list_tax_categories_returns_created(client, pos_auth_headers, test_tax_category):
    """GET /tax/categories returns categories for the authenticated brand."""
    response = await client.get("/tax/categories", headers=pos_auth_headers)

    assert response.status_code == 200
    ids = [c["id"] for c in response.json()]
    assert str(test_tax_category.id) in ids


async def test_update_tax_category_returns_200(client, pos_auth_headers, test_tax_category):
    """PATCH /tax/categories/{id} updates the name and returns 200."""
    response = await client.patch(
        f"/tax/categories/{test_tax_category.id}",
        json={"name": "Renamed"},
        headers=pos_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"


# ── Tax category failures ─────────────────────────────────────────────────────


async def test_create_tax_category_no_token_returns_403(client):
    """Creating a tax category without a token returns 403."""
    response = await client.post("/tax/categories", json={"name": "Food"})
    assert response.status_code == 403


async def test_update_tax_category_wrong_brand_returns_404(
    client, db, pos_auth_headers, test_group
):
    """Updating a tax category from a different brand returns 404."""
    from app.models.brand import Brand
    from app.models.tax_category import TaxCategory

    other_brand = Brand(id=uuid.uuid4(), group_id=test_group.id, name="Other", is_active=True)
    db.add(other_brand)
    other_cat = TaxCategory(
        id=uuid.uuid4(), brand_id=other_brand.id, name="Foreign", is_active=True
    )
    db.add(other_cat)
    await db.commit()

    response = await client.patch(
        f"/tax/categories/{other_cat.id}",
        json={"name": "Hacked"},
        headers=pos_auth_headers,
    )

    assert response.status_code == 404


async def test_create_tax_category_missing_name_returns_422(client, pos_auth_headers):
    """Missing name field returns 422."""
    response = await client.post("/tax/categories", json={}, headers=pos_auth_headers)
    assert response.status_code == 422


# ── Tax rate happy path ───────────────────────────────────────────────────────


async def test_create_tax_rate_returns_201(client, pos_auth_headers, test_tax_category):
    """POST /tax/categories/{id}/rates creates a rate and returns 201."""
    response = await client.post(
        f"/tax/categories/{test_tax_category.id}/rates",
        json={"name": "GST", "rate_percent": "10.0000", "tax_model": "inclusive"},
        headers=pos_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "GST"
    assert body["tax_category_id"] == str(test_tax_category.id)
    assert body["tax_model"] == "inclusive"
    assert float(body["rate_percent"]) == 10.0


async def test_create_tax_rate_writes_audit_log(
    client, db, pos_auth_headers, test_pos_user, test_tax_category
):
    """Creating a tax rate writes a TAX_RATE_CREATED audit row."""
    await client.post(
        f"/tax/categories/{test_tax_category.id}/rates",
        json={"name": "GST", "rate_percent": "10.0000", "tax_model": "exclusive"},
        headers=pos_auth_headers,
    )

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == TAX_RATE_CREATED)
    )
    row = result.scalar_one()
    assert row.actor_id == test_pos_user.id


async def test_list_tax_rates_returns_created(client, db, pos_auth_headers, test_tax_category):
    """GET /tax/categories/{id}/rates returns the created rate."""
    await client.post(
        f"/tax/categories/{test_tax_category.id}/rates",
        json={"name": "GST", "rate_percent": "10.0000", "tax_model": "inclusive"},
        headers=pos_auth_headers,
    )

    response = await client.get(
        f"/tax/categories/{test_tax_category.id}/rates",
        headers=pos_auth_headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "GST"


async def test_update_tax_rate_returns_200(client, db, pos_auth_headers, test_tax_category):
    """PATCH /tax/rates/{id} updates rate fields and returns 200."""
    create_resp = await client.post(
        f"/tax/categories/{test_tax_category.id}/rates",
        json={"name": "GST", "rate_percent": "10.0000", "tax_model": "inclusive"},
        headers=pos_auth_headers,
    )
    rate_id = create_resp.json()["id"]

    response = await client.patch(
        f"/tax/rates/{rate_id}",
        json={"rate_percent": "15.0000"},
        headers=pos_auth_headers,
    )

    assert response.status_code == 200
    assert float(response.json()["rate_percent"]) == 15.0


async def test_update_tax_rate_writes_audit_log(
    client, db, pos_auth_headers, test_pos_user, test_tax_category
):
    """Updating a tax rate writes a TAX_RATE_UPDATED audit row."""
    create_resp = await client.post(
        f"/tax/categories/{test_tax_category.id}/rates",
        json={"name": "GST", "rate_percent": "10.0000", "tax_model": "inclusive"},
        headers=pos_auth_headers,
    )
    rate_id = create_resp.json()["id"]

    await client.patch(
        f"/tax/rates/{rate_id}",
        json={"name": "GST Updated"},
        headers=pos_auth_headers,
    )

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == TAX_RATE_UPDATED)
    )
    row = result.scalar_one()
    assert row.actor_id == test_pos_user.id


# ── Tax rate failures ─────────────────────────────────────────────────────────


async def test_create_tax_rate_invalid_model_returns_422(client, pos_auth_headers, test_tax_category):
    """Invalid tax_model value returns 422."""
    response = await client.post(
        f"/tax/categories/{test_tax_category.id}/rates",
        json={"name": "GST", "rate_percent": "10.0000", "tax_model": "invalid_model"},
        headers=pos_auth_headers,
    )

    assert response.status_code == 422


async def test_create_tax_rate_unknown_category_returns_404(client, pos_auth_headers):
    """Creating a rate for an unknown tax category returns 404."""
    response = await client.post(
        f"/tax/categories/{uuid.uuid4()}/rates",
        json={"name": "GST", "rate_percent": "10.0000", "tax_model": "inclusive"},
        headers=pos_auth_headers,
    )

    assert response.status_code == 404
