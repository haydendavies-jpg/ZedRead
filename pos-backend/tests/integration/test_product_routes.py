"""Integration tests for product CRUD routes.

Covers:
1. Happy path — create/list/get/update/deactivate product
2. Auth failure — no token returns 403
3. Business rules — cross-brand category 400; unknown product 404; deactivate already inactive 409
4. Invalid input — missing required fields return 422
5. Audit log — PRODUCT_CREATED, PRODUCT_UPDATED, PRODUCT_DEACTIVATED written
"""

import uuid

import pytest
from sqlalchemy import select

from app.constants.audit_actions import PRODUCT_CREATED, PRODUCT_DEACTIVATED, PRODUCT_UPDATED
from app.models.audit_log import AuditLog
from app.models.category import Category

pytestmark = pytest.mark.asyncio


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_or_create_category(db, brand_id) -> uuid.UUID:
    """Return the first category ID for a brand, creating one if needed."""
    result = await db.execute(
        select(Category).where(Category.brand_id == brand_id).limit(1)
    )
    cat = result.scalar_one_or_none()
    if cat:
        return cat.id

    cat = Category(
        id=uuid.uuid4(),
        brand_id=brand_id,
        name="Uncategorised",
        is_system=True,
        is_active=True,
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat.id


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_create_product_returns_201(client, db, pos_auth_headers, test_brand):
    """POST /products creates a product and returns 201 with correct shape."""
    category_id = await _get_or_create_category(db, test_brand.id)

    response = await client.post(
        "/products",
        json={
            "category_id": str(category_id),
            "name": "Chicken Burger",
            "base_price_cents": 1299,
        },
        headers=pos_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Chicken Burger"
    assert body["base_price_cents"] == 1299
    assert body["brand_id"] == str(test_brand.id)
    assert body["is_active"] is True


async def test_create_product_writes_audit_log(client, db, pos_auth_headers, test_brand, test_pos_user):
    """Creating a product writes a PRODUCT_CREATED audit row."""
    category_id = await _get_or_create_category(db, test_brand.id)

    await client.post(
        "/products",
        json={"category_id": str(category_id), "name": "Fries", "base_price_cents": 500},
        headers=pos_auth_headers,
    )

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == PRODUCT_CREATED)
    )
    row = result.scalar_one()
    assert row.actor_id == test_pos_user.id


async def test_list_products_returns_created(client, pos_auth_headers, test_product):
    """GET /products returns the seeded product."""
    response = await client.get("/products", headers=pos_auth_headers)

    assert response.status_code == 200
    ids = [p["id"] for p in response.json()]
    assert str(test_product.id) in ids


async def test_get_product_returns_200(client, pos_auth_headers, test_product):
    """GET /products/{id} returns the product."""
    response = await client.get(f"/products/{test_product.id}", headers=pos_auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(test_product.id)
    assert response.json()["name"] == test_product.name


async def test_update_product_returns_200(client, pos_auth_headers, test_product):
    """PATCH /products/{id} updates the name and price."""
    response = await client.patch(
        f"/products/{test_product.id}",
        json={"name": "Updated Burger", "base_price_cents": 1600},
        headers=pos_auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Updated Burger"
    assert body["base_price_cents"] == 1600


async def test_update_product_writes_audit_log(
    client, db, pos_auth_headers, test_product, test_pos_user
):
    """Updating a product writes a PRODUCT_UPDATED audit row."""
    await client.patch(
        f"/products/{test_product.id}",
        json={"name": "New Name"},
        headers=pos_auth_headers,
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.action == PRODUCT_UPDATED,
            AuditLog.entity_id == str(test_product.id),
        )
    )
    row = result.scalar_one()
    assert row.actor_id == test_pos_user.id


async def test_deactivate_product_returns_200(client, pos_auth_headers, test_product):
    """DELETE /products/{id} soft-deletes and returns 200."""
    response = await client.delete(
        f"/products/{test_product.id}",
        headers=pos_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_deactivate_product_writes_audit_log(
    client, db, pos_auth_headers, test_product, test_pos_user
):
    """Deactivating a product writes a PRODUCT_DEACTIVATED audit row."""
    await client.delete(f"/products/{test_product.id}", headers=pos_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.action == PRODUCT_DEACTIVATED,
            AuditLog.entity_id == str(test_product.id),
        )
    )
    row = result.scalar_one()
    assert row.actor_id == test_pos_user.id


# ── Business rules ────────────────────────────────────────────────────────────


async def test_create_product_cross_brand_category_returns_400(
    client, db, pos_auth_headers, test_group
):
    """Assigning a product to a category from a different brand returns 400."""
    from app.models.brand import Brand

    other_brand = Brand(id=uuid.uuid4(), group_id=test_group.id, name="Other Brand", is_active=True)
    db.add(other_brand)
    other_cat = Category(
        id=uuid.uuid4(),
        brand_id=other_brand.id,
        name="Other Cat",
        is_system=False,
        is_active=True,
    )
    db.add(other_cat)
    await db.commit()

    response = await client.post(
        "/products",
        json={
            "category_id": str(other_cat.id),
            "name": "Cross Brand Product",
            "base_price_cents": 1000,
        },
        headers=pos_auth_headers,
    )

    assert response.status_code == 400
    assert "brand" in response.json()["detail"].lower()


async def test_get_product_not_found_returns_404(client, pos_auth_headers):
    """GET /products/{id} with unknown ID returns 404."""
    response = await client.get(f"/products/{uuid.uuid4()}", headers=pos_auth_headers)
    assert response.status_code == 404


async def test_deactivate_already_inactive_returns_409(
    client, db, pos_auth_headers, test_product
):
    """Deactivating an already-inactive product returns 409."""
    await client.delete(f"/products/{test_product.id}", headers=pos_auth_headers)

    response = await client.delete(f"/products/{test_product.id}", headers=pos_auth_headers)

    assert response.status_code == 409


async def test_list_products_filter_by_category(client, db, pos_auth_headers, test_brand, test_product):
    """GET /products?category_id=X returns only products in that category."""
    response = await client.get(
        f"/products?category_id={test_product.category_id}",
        headers=pos_auth_headers,
    )

    assert response.status_code == 200
    for product in response.json():
        assert product["category_id"] == str(test_product.category_id)


# ── Auth / input failures ─────────────────────────────────────────────────────


async def test_list_products_no_token_returns_403(client):
    """GET /products without auth token returns 403."""
    response = await client.get("/products")
    assert response.status_code == 403


async def test_create_product_missing_required_fields_returns_422(client, pos_auth_headers):
    """Missing name and base_price_cents returns 422."""
    response = await client.post(
        "/products",
        json={"category_id": str(uuid.uuid4())},
        headers=pos_auth_headers,
    )

    assert response.status_code == 422


async def test_create_product_negative_price_returns_422(client, db, pos_auth_headers, test_brand):
    """Negative base_price_cents returns 422."""
    category_id = await _get_or_create_category(db, test_brand.id)

    response = await client.post(
        "/products",
        json={"category_id": str(category_id), "name": "Bad Price", "base_price_cents": -1},
        headers=pos_auth_headers,
    )

    assert response.status_code == 422
