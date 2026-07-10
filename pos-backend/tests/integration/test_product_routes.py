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

from app.constants.audit_actions import (
    PRODUCT_CREATED,
    PRODUCT_DEACTIVATED,
    PRODUCT_REACTIVATED,
    PRODUCT_UPDATED,
)
from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.reporting_group import ReportingGroup

pytestmark = pytest.mark.asyncio


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_or_create_reporting_group(db, brand_id) -> uuid.UUID:
    """Return the default reporting group ID for a brand, creating one if needed."""
    result = await db.execute(
        select(ReportingGroup).where(ReportingGroup.brand_id == brand_id, ReportingGroup.is_default == True)  # noqa: E712
    )
    group = result.scalar_one_or_none()
    if group:
        return group.id

    group = ReportingGroup(
        id=uuid.uuid4(),
        brand_id=brand_id,
        name="Default",
        is_default=True,
        is_system=True,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group.id


async def _get_or_create_category(db, brand_id) -> uuid.UUID:
    """Return the first category ID for a brand, creating one if needed."""
    result = await db.execute(
        select(Category).where(Category.brand_id == brand_id).limit(1)
    )
    cat = result.scalar_one_or_none()
    if cat:
        return cat.id

    reporting_group_id = await _get_or_create_reporting_group(db, brand_id)
    cat = Category(
        id=uuid.uuid4(),
        brand_id=brand_id,
        reporting_group_id=reporting_group_id,
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
    assert body["ref"].startswith("PRD-")
    assert body["print_name"] is None
    assert body["effective_print_name"] == "Chicken Burger"
    assert body["is_open_item"] is False


async def test_create_product_with_print_name_and_open_item(client, db, pos_auth_headers, test_brand):
    """print_name and is_open_item round-trip through create."""
    category_id = await _get_or_create_category(db, test_brand.id)

    response = await client.post(
        "/products",
        json={
            "category_id": str(category_id),
            "name": "Misc Item",
            "print_name": "MISC",
            "base_price_cents": 0,
            "is_open_item": True,
        },
        headers=pos_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["print_name"] == "MISC"
    assert body["effective_print_name"] == "MISC"
    assert body["is_open_item"] is True


async def test_update_product_print_name_and_open_item(client, pos_auth_headers, test_product):
    """PATCH /products/{id} updates print_name and is_open_item."""
    response = await client.patch(
        f"/products/{test_product.id}",
        json={"print_name": "DOCKET NAME", "is_open_item": True},
        headers=pos_auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["print_name"] == "DOCKET NAME"
    assert body["effective_print_name"] == "DOCKET NAME"
    assert body["is_open_item"] is True


async def test_create_product_writes_audit_log(client, db, pos_auth_headers, test_brand, test_user):
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
    assert row.actor_id == test_user.id


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
    client, db, pos_auth_headers, test_product, test_user
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
    assert row.actor_id == test_user.id


async def test_deactivate_product_returns_200(client, pos_auth_headers, test_product):
    """DELETE /products/{id} soft-deletes and returns 200."""
    response = await client.delete(
        f"/products/{test_product.id}",
        headers=pos_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_deactivate_product_writes_audit_log(
    client, db, pos_auth_headers, test_product, test_user
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
    assert row.actor_id == test_user.id


# ── Business rules ────────────────────────────────────────────────────────────


async def test_create_product_cross_brand_category_returns_400(
    client, db, pos_auth_headers, test_group
):
    """Assigning a product to a category from a different brand returns 400."""
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
    other_reporting_group_id = await _get_or_create_reporting_group(db, other_brand.id)
    other_cat = Category(
        id=uuid.uuid4(),
        brand_id=other_brand.id,
        reporting_group_id=other_reporting_group_id,
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


# ── Stage 20 — joined columns, include_inactive, activate ───────────────────


async def test_list_products_includes_joined_category_and_reporting_group(
    client, pos_auth_headers, test_product, test_reporting_group
):
    """GET /products rows carry the joined category_name/reporting_group_id/reporting_group_name."""
    response = await client.get("/products", headers=pos_auth_headers)

    assert response.status_code == 200
    row = next(p for p in response.json() if p["id"] == str(test_product.id))
    assert row["category_name"]
    assert row["reporting_group_id"] == str(test_reporting_group.id)
    assert row["reporting_group_name"] == test_reporting_group.name


async def test_list_products_excludes_inactive_by_default(client, pos_auth_headers, test_product):
    """GET /products omits soft-deleted products unless include_inactive=true."""
    await client.delete(f"/products/{test_product.id}", headers=pos_auth_headers)

    response = await client.get("/products", headers=pos_auth_headers)

    assert response.status_code == 200
    ids = [p["id"] for p in response.json()]
    assert str(test_product.id) not in ids


async def test_list_products_include_inactive_returns_deactivated_row(client, pos_auth_headers, test_product):
    """GET /products?include_inactive=true includes soft-deleted products."""
    await client.delete(f"/products/{test_product.id}", headers=pos_auth_headers)

    response = await client.get("/products?include_inactive=true", headers=pos_auth_headers)

    assert response.status_code == 200
    row = next(p for p in response.json() if p["id"] == str(test_product.id))
    assert row["is_active"] is False


async def test_activate_product_returns_200_and_reactivates(client, pos_auth_headers, test_product):
    """POST /products/{id}/activate reactivates a deactivated product."""
    await client.delete(f"/products/{test_product.id}", headers=pos_auth_headers)

    response = await client.post(f"/products/{test_product.id}/activate", headers=pos_auth_headers)

    assert response.status_code == 200
    assert response.json()["is_active"] is True


async def test_activate_product_writes_audit_log(client, db, pos_auth_headers, test_product, test_user):
    """Reactivating a product writes a PRODUCT_REACTIVATED audit row."""
    await client.delete(f"/products/{test_product.id}", headers=pos_auth_headers)

    await client.post(f"/products/{test_product.id}/activate", headers=pos_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.action == PRODUCT_REACTIVATED,
            AuditLog.entity_id == str(test_product.id),
        )
    )
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_activate_already_active_product_is_idempotent(client, pos_auth_headers, test_product):
    """POST /products/{id}/activate on an already-active product is a silent no-op, not an error."""
    response = await client.post(f"/products/{test_product.id}/activate", headers=pos_auth_headers)

    assert response.status_code == 200
    assert response.json()["is_active"] is True


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


# ── Tax-inclusive/exclusive price derivation ─────────────────────────────────


async def _seed_au_inclusive_template(db, rate_percent: str = "10.0000") -> None:
    """Seed an AU country-level template with a single inclusive GST rate."""
    from decimal import Decimal

    from app.models.tax_template import TaxTemplate
    from app.models.tax_template_rate import TaxTemplateRate

    template = TaxTemplate(id=uuid.uuid4(), name="Australia GST", country="AU", is_active=True)
    db.add(template)
    await db.flush()
    db.add(
        TaxTemplateRate(
            id=uuid.uuid4(),
            tax_template_id=template.id,
            name="GST",
            rate_percent=Decimal(rate_percent),
            tax_model="inclusive",
            is_active=True,
        )
    )
    await db.commit()


async def test_create_product_derives_ex_price_from_country_rate(client, db, pos_auth_headers, test_brand):
    """A product's exclusive price is derived from the brand's country inclusive rate at save."""
    await _seed_au_inclusive_template(db)  # test_brand.country == "AU"
    category_id = await _get_or_create_category(db, test_brand.id)

    response = await client.post(
        "/products",
        json={"category_id": str(category_id), "name": "Latte", "base_price_cents": 1100},
        headers=pos_auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    # inc 1100 at 10% inclusive → ex = round(1100 / 1.1) = 1000
    assert body["base_price_cents"] == 1100
    assert body["price_ex_cents"] == 1000
    assert body["is_taxable"] is True


async def test_create_product_no_template_ex_equals_inc(client, db, pos_auth_headers, test_brand):
    """With no matching country template the exclusive price equals the inclusive price."""
    category_id = await _get_or_create_category(db, test_brand.id)

    response = await client.post(
        "/products",
        json={"category_id": str(category_id), "name": "Water", "base_price_cents": 500, "is_taxable": False},
        headers=pos_auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["price_ex_cents"] == 500
    assert body["is_taxable"] is False


async def test_update_product_reprices_ex_on_inclusive_change(client, db, pos_auth_headers, test_brand):
    """Changing the inclusive price re-derives the exclusive price."""
    await _seed_au_inclusive_template(db)
    category_id = await _get_or_create_category(db, test_brand.id)

    created = await client.post(
        "/products",
        json={"category_id": str(category_id), "name": "Mocha", "base_price_cents": 1100},
        headers=pos_auth_headers,
    )
    product_id = created.json()["id"]

    updated = await client.patch(
        f"/products/{product_id}",
        json={"base_price_cents": 2200},
        headers=pos_auth_headers,
    )
    assert updated.status_code == 200
    body = updated.json()
    # inc 2200 at 10% inclusive → ex = 2000
    assert body["base_price_cents"] == 2200
    assert body["price_ex_cents"] == 2000


async def test_create_tax_free_product_not_rate_stripped_when_template_exists(
    client, db, pos_auth_headers, test_brand
):
    """A Tax Free product keeps its entered price exactly, even with a country rate active.

    Regression test: price_ex_cents must equal the entered price when is_taxable
    is false — there is no tax to strip out, so deriving via the country rate
    would silently undercharge (e.g. $10.00 becoming $9.09 at 10% GST).
    """
    await _seed_au_inclusive_template(db)
    category_id = await _get_or_create_category(db, test_brand.id)

    response = await client.post(
        "/products",
        json={
            "category_id": str(category_id),
            "name": "Gift Card",
            "base_price_cents": 1000,
            "is_taxable": False,
        },
        headers=pos_auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["base_price_cents"] == 1000
    assert body["price_ex_cents"] == 1000
    assert body["is_taxable"] is False


async def test_toggle_to_tax_free_reprices_without_rate_stripping(
    client, db, pos_auth_headers, test_brand
):
    """Switching an existing taxable product to Tax Free recomputes price_ex_cents
    to equal the inclusive price, undoing the previously-stripped GST."""
    await _seed_au_inclusive_template(db)
    category_id = await _get_or_create_category(db, test_brand.id)

    created = await client.post(
        "/products",
        json={"category_id": str(category_id), "name": "Coffee", "base_price_cents": 1100},
        headers=pos_auth_headers,
    )
    product_id = created.json()["id"]
    assert created.json()["price_ex_cents"] == 1000  # GST stripped while taxable

    updated = await client.patch(
        f"/products/{product_id}",
        json={"is_taxable": False},
        headers=pos_auth_headers,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["is_taxable"] is False
    # No price change was submitted — base_price_cents stays 1100, but ex must
    # now equal it exactly since the product no longer carries any tax.
    assert body["base_price_cents"] == 1100
    assert body["price_ex_cents"] == 1100


async def test_toggle_to_taxed_reapplies_rate_derivation(
    client, db, pos_auth_headers, test_brand
):
    """Switching an existing tax-free product to Taxed re-derives the exclusive
    price from the country rate instead of leaving it equal to the inclusive price."""
    await _seed_au_inclusive_template(db)
    category_id = await _get_or_create_category(db, test_brand.id)

    created = await client.post(
        "/products",
        json={
            "category_id": str(category_id),
            "name": "Book",
            "base_price_cents": 1100,
            "is_taxable": False,
        },
        headers=pos_auth_headers,
    )
    product_id = created.json()["id"]
    assert created.json()["price_ex_cents"] == 1100  # no tax while tax-free

    updated = await client.patch(
        f"/products/{product_id}",
        json={"is_taxable": True},
        headers=pos_auth_headers,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["is_taxable"] is True
    assert body["base_price_cents"] == 1100
    assert body["price_ex_cents"] == 1000  # GST now stripped out
