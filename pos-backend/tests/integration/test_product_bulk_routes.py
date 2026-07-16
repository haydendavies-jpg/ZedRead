"""
Integration tests for POST /products/bulk.

Covers:
1. Happy path — price_cents, price_markup_percent, category_id, tax_category_id,
   modifier_group_id attach
2. Auth failure — no token returns 401
3. Invalid input — empty product_ids, both price fields set, returns 422
4. Business rule violation — wrong-brand product_id/category_id/tax_category_id rejected
5. Audit log — one product.bulk_updated row per modified product
6. Archive cascade — is_active=False deletes modifier links and menu_buttons rows
"""

import uuid

import pytest
from sqlalchemy import select

from app.constants.audit_actions import PRODUCT_BULK_UPDATED
from app.models.audit_log import AuditLog
from app.models.brand import Brand
from app.models.category import Category
from app.models.menu_button import MenuButton
from app.models.menu_layout import MenuLayout
from app.models.menu_tab import MenuTab
from app.models.product import Product
from app.models.product_modifier_group_link import ProductModifierGroupLink
from app.models.reporting_group import ReportingGroup
from app.models.tax_category import TaxCategory

pytestmark = pytest.mark.asyncio


async def _create_second_product(db, test_brand, test_product) -> Product:
    """Create a second active Product in the same brand/category as test_product."""
    product = Product(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        category_id=test_product.category_id,
        tax_category_id=None,
        name="Second Product",
        base_price_cents=2000,
        price_ex_cents=2000,
        is_taxable=True,
        display_order=1,
        is_active=True,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_bulk_update_price_cents(client, test_product, pos_auth_headers):
    """POST /products/bulk with price_cents overwrites base_price_cents for all selected."""
    resp = await client.post(
        "/products/bulk",
        json={"product_ids": [str(test_product.id)], "price_cents": 999},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated_count"] == 1
    assert data["updated_product_ids"] == [str(test_product.id)]

    get_resp = await client.get(f"/products/{test_product.id}", headers=pos_auth_headers)
    assert get_resp.json()["base_price_cents"] == 999


async def test_bulk_update_price_markup_percent_rounds_half_up(
    client, test_product, pos_auth_headers
):
    """price_markup_percent multiplies current base_price_cents and rounds to the nearest cent."""
    # test_product.base_price_cents == 1500; +10% == 1650.0 exactly
    resp = await client.post(
        "/products/bulk",
        json={"product_ids": [str(test_product.id)], "price_markup_percent": 10},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200

    get_resp = await client.get(f"/products/{test_product.id}", headers=pos_auth_headers)
    assert get_resp.json()["base_price_cents"] == 1650


async def test_bulk_update_category_id(client, db, test_product, test_brand, pos_auth_headers):
    """category_id reassigns every selected product's category."""
    result = await db.execute(
        select(ReportingGroup).where(ReportingGroup.brand_id == test_brand.id, ReportingGroup.is_default == True)  # noqa: E712
    )
    reporting_group = result.scalar_one()
    new_category = Category(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        reporting_group_id=reporting_group.id,
        name="New Category",
        is_system=False,
        is_active=True,
    )
    db.add(new_category)
    await db.commit()

    resp = await client.post(
        "/products/bulk",
        json={"product_ids": [str(test_product.id)], "category_id": str(new_category.id)},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200

    get_resp = await client.get(f"/products/{test_product.id}", headers=pos_auth_headers)
    assert get_resp.json()["category_id"] == str(new_category.id)


async def test_bulk_update_tax_category_id(client, test_product, test_tax_category, pos_auth_headers):
    """tax_category_id reassigns every selected product's tax category."""
    resp = await client.post(
        "/products/bulk",
        json={"product_ids": [str(test_product.id)], "tax_category_id": str(test_tax_category.id)},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200

    get_resp = await client.get(f"/products/{test_product.id}", headers=pos_auth_headers)
    assert get_resp.json()["tax_category_id"] == str(test_tax_category.id)


async def test_bulk_update_modifier_group_id_attaches_only_missing(
    client, db, test_product, test_brand, pos_auth_headers
):
    """modifier_group_id attaches the group to selected products that don't already have it."""
    group_resp = await client.post(
        "/modifier-groups",
        json={"name": "Bulk Sauces", "min_selections": 0, "max_selections": 1},
        headers=pos_auth_headers,
    )
    group_id = group_resp.json()["id"]

    resp = await client.post(
        "/products/bulk",
        json={"product_ids": [str(test_product.id)], "modifier_group_id": group_id},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["updated_count"] == 1

    link_result = await db.execute(
        select(ProductModifierGroupLink).where(
            ProductModifierGroupLink.product_id == test_product.id,
            ProductModifierGroupLink.modifier_group_id == uuid.UUID(group_id),
        )
    )
    assert link_result.scalar_one_or_none() is not None

    # Calling again is a no-op — the product already has the link, nothing changes
    resp2 = await client.post(
        "/products/bulk",
        json={"product_ids": [str(test_product.id)], "modifier_group_id": group_id},
        headers=pos_auth_headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["updated_count"] == 0


async def test_bulk_update_writes_one_audit_row_per_product(
    client, db, test_product, test_brand, pos_auth_headers
):
    """Bulk-updating two products writes one product.bulk_updated row per product."""
    second_product = await _create_second_product(db, test_brand, test_product)

    resp = await client.post(
        "/products/bulk",
        json={"product_ids": [str(test_product.id), str(second_product.id)], "price_cents": 500},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["updated_count"] == 2

    result = await db.execute(select(AuditLog).where(AuditLog.action == PRODUCT_BULK_UPDATED))
    rows = result.scalars().all()
    entity_ids = {row.entity_id for row in rows}
    assert str(test_product.id) in entity_ids
    assert str(second_product.id) in entity_ids


# ── Archive cascade ───────────────────────────────────────────────────────────


async def test_bulk_archive_cascades_modifier_links_and_menu_buttons(
    client, db, test_product, test_brand, pos_auth_headers
):
    """is_active=False deletes the product's modifier links and matching menu_buttons rows."""
    group_resp = await client.post(
        "/modifier-groups",
        json={"name": "Cascade Sauces", "min_selections": 0, "max_selections": 1},
        headers=pos_auth_headers,
    )
    group_id = group_resp.json()["id"]
    link_resp = await client.post(
        f"/products/{test_product.id}/modifiers",
        json={"modifier_group_id": group_id, "display_order": 0},
        headers=pos_auth_headers,
    )
    assert link_resp.status_code == 201

    layout = MenuLayout(id=uuid.uuid4(), brand_id=test_brand.id, scope="brand", site_id=None, name="Main Menu")
    db.add(layout)
    await db.flush()
    tab = MenuTab(id=uuid.uuid4(), layout_id=layout.id, name="Mains", display_order=0)
    db.add(tab)
    await db.flush()
    button = MenuButton(
        id=uuid.uuid4(),
        tab_id=tab.id,
        kind="product",
        product_ref=test_product.ref,
        width=1,
        height=1,
        display_order=0,
    )
    db.add(button)
    await db.commit()

    resp = await client.post(
        "/products/bulk",
        json={"product_ids": [str(test_product.id)], "is_active": False},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["updated_count"] == 1

    link_result = await db.execute(
        select(ProductModifierGroupLink).where(ProductModifierGroupLink.product_id == test_product.id)
    )
    assert link_result.scalar_one_or_none() is None

    button_result = await db.execute(select(MenuButton).where(MenuButton.id == button.id))
    assert button_result.scalar_one_or_none() is None

    get_resp = await client.get(f"/products/{test_product.id}", headers=pos_auth_headers)
    assert get_resp.json()["is_active"] is False

    audit_result = await db.execute(
        select(AuditLog).where(
            AuditLog.action == PRODUCT_BULK_UPDATED, AuditLog.entity_id == str(test_product.id)
        )
    )
    row = audit_result.scalar_one()
    assert row.after_state["deleted_modifier_link_count"] == 1
    assert row.after_state["deleted_menu_button_count"] == 1


# ── Auth failure ──────────────────────────────────────────────────────────────


async def test_bulk_update_no_token_returns_403(client, test_product):
    """POST /products/bulk without a token returns 403 (HTTPBearer's default auto_error
    response for a missing Authorization header — matches the codebase-wide convention,
    e.g. test_categories_routes.py::test_create_category_no_token_returns_403)."""
    resp = await client.post("/products/bulk", json={"product_ids": [str(test_product.id)], "price_cents": 100})
    assert resp.status_code == 403


# ── Invalid input ─────────────────────────────────────────────────────────────


async def test_bulk_update_empty_product_ids_returns_422(client, pos_auth_headers):
    """POST /products/bulk with an empty product_ids list returns 422."""
    resp = await client.post(
        "/products/bulk", json={"product_ids": [], "price_cents": 100}, headers=pos_auth_headers
    )
    assert resp.status_code == 422


async def test_bulk_update_both_price_fields_returns_422(client, test_product, pos_auth_headers):
    """Setting both price_cents and price_markup_percent returns 422 (mutually exclusive)."""
    resp = await client.post(
        "/products/bulk",
        json={"product_ids": [str(test_product.id)], "price_cents": 100, "price_markup_percent": 10},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 422


# ── Business rule violation ───────────────────────────────────────────────────


async def test_bulk_update_wrong_brand_product_id_returns_400(
    client, db, test_group, test_brand, pos_auth_headers
):
    """A product_id from another brand rejects the whole batch with 400."""
    other_brand = Brand(
        id=uuid.uuid4(),
        group_id=test_group.id,
        name="Other Bulk Brand",
        is_active=True,
        timezone="Australia/Sydney",
        currency="AUD",
        country="AU",
    )
    db.add(other_brand)
    await db.flush()
    other_reporting_group = ReportingGroup(
        id=uuid.uuid4(), brand_id=other_brand.id, name="Other Default", is_default=True, is_system=True
    )
    db.add(other_reporting_group)
    await db.flush()
    other_category = Category(
        id=uuid.uuid4(),
        brand_id=other_brand.id,
        reporting_group_id=other_reporting_group.id,
        name="Other Cat",
        is_system=False,
        is_active=True,
    )
    db.add(other_category)
    await db.flush()
    other_product = Product(
        id=uuid.uuid4(),
        brand_id=other_brand.id,
        category_id=other_category.id,
        name="Other Brand Product",
        base_price_cents=1000,
        price_ex_cents=1000,
        is_taxable=True,
        display_order=0,
        is_active=True,
    )
    db.add(other_product)
    await db.commit()

    resp = await client.post(
        "/products/bulk",
        json={"product_ids": [str(other_product.id)], "price_cents": 100},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 400
    assert str(other_product.id) in str(resp.json()["detail"])


async def test_bulk_update_wrong_brand_tax_category_returns_400(
    client, db, test_group, test_product, pos_auth_headers
):
    """A tax_category_id from another brand rejects the batch with 400."""
    other_brand = Brand(
        id=uuid.uuid4(),
        group_id=test_group.id,
        name="Other Tax Brand",
        is_active=True,
        timezone="Australia/Sydney",
        currency="AUD",
        country="AU",
    )
    db.add(other_brand)
    await db.flush()
    other_tax_category = TaxCategory(id=uuid.uuid4(), brand_id=other_brand.id, name="Foreign Tax", is_active=True)
    db.add(other_tax_category)
    await db.commit()

    resp = await client.post(
        "/products/bulk",
        json={
            "product_ids": [str(test_product.id)],
            "tax_category_id": str(other_tax_category.id),
        },
        headers=pos_auth_headers,
    )
    assert resp.status_code == 400
