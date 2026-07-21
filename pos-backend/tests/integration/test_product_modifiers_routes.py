"""
Integration tests for the product-modifiers attach/available listing,
whole-list reorder, and the modifier group "used by products" listing.

Covers:
1. Happy path — GET attached/available split, PATCH reorder resequencing,
   GET /modifier-groups/{id}/products
2. Auth failure — no token returns 401
3. Invalid input — malformed body returns 422
4. Business rule violation — a modifier_group_id from another brand is rejected
5. Audit log — product.modifiers.reordered written on reorder
"""

import uuid

import pytest
from sqlalchemy import select

from app.constants.audit_actions import PRODUCT_MODIFIERS_REORDERED
from app.models.audit_log import AuditLog
from app.models.brand import Brand
from app.models.category import Category
from app.models.modifier_group import ModifierGroup
from app.models.product import Product
from app.models.reporting_group import ReportingGroup

pytestmark = pytest.mark.asyncio


async def _create_group(client, headers, name: str, max_selections: int = 1) -> str:
    """Create a modifier group via the API and return its id."""
    resp = await client.post(
        "/modifier-groups",
        json={"name": name, "min_selections": 0, "max_selections": max_selections},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_list_product_modifiers_splits_attached_and_available(
    client, pos_auth_headers, test_product
):
    """GET /products/{id}/modifiers returns attached (linked) and available (not linked) groups."""
    attached_group_id = await _create_group(client, pos_auth_headers, "Sauces")
    available_group_id = await _create_group(client, pos_auth_headers, "Sides")

    link_resp = await client.post(
        f"/products/{test_product.id}/modifiers",
        json={"modifier_group_id": attached_group_id, "display_order": 0},
        headers=pos_auth_headers,
    )
    assert link_resp.status_code == 201

    resp = await client.get(f"/products/{test_product.id}/modifiers", headers=pos_auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    attached_ids = {item["modifier_group_id"] for item in data["attached"]}
    available_ids = {item["modifier_group_id"] for item in data["available"]}
    assert attached_ids == {attached_group_id}
    assert available_group_id in available_ids
    assert attached_group_id not in available_ids


async def test_reorder_product_modifiers_resequences_display_order(
    client, pos_auth_headers, test_product
):
    """PATCH .../modifiers/reorder attaches/detaches to match the list and resequences order."""
    group_a = await _create_group(client, pos_auth_headers, "Group A")
    group_b = await _create_group(client, pos_auth_headers, "Group B")
    group_c = await _create_group(client, pos_auth_headers, "Group C")

    # Attach A and B in that order first
    await client.post(
        f"/products/{test_product.id}/modifiers",
        json={"modifier_group_id": group_a, "display_order": 0},
        headers=pos_auth_headers,
    )
    await client.post(
        f"/products/{test_product.id}/modifiers",
        json={"modifier_group_id": group_b, "display_order": 1},
        headers=pos_auth_headers,
    )

    # Reorder: drop A, keep B, add C — full desired set in [C, B] order
    resp = await client.patch(
        f"/products/{test_product.id}/modifiers/reorder",
        json={"modifier_group_ids": [group_c, group_b]},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    attached = sorted(data["attached"], key=lambda item: item["display_order"])
    assert [item["modifier_group_id"] for item in attached] == [group_c, group_b]
    assert [item["display_order"] for item in attached] == [0, 1]

    available_ids = {item["modifier_group_id"] for item in data["available"]}
    assert group_a in available_ids  # detached, now available again


async def test_reorder_product_modifiers_writes_audit_log(
    client, db, pos_auth_headers, test_product
):
    """Reordering writes a single 'product.modifiers.reordered' audit row against the product."""
    group_a = await _create_group(client, pos_auth_headers, "Group A")

    resp = await client.patch(
        f"/products/{test_product.id}/modifiers/reorder",
        json={"modifier_group_ids": [group_a]},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 200

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.action == PRODUCT_MODIFIERS_REORDERED,
            AuditLog.entity_id == str(test_product.id),
        )
    )
    row = result.scalar_one()
    assert row.after_state["modifier_group_ids"] == [group_a]


async def test_list_products_for_modifier_group(client, pos_auth_headers, test_product):
    """GET /modifier-groups/{id}/products lists the products linked to that group."""
    group_id = await _create_group(client, pos_auth_headers, "Toppings")

    await client.post(
        f"/products/{test_product.id}/modifiers",
        json={"modifier_group_id": group_id, "display_order": 0},
        headers=pos_auth_headers,
    )

    resp = await client.get(f"/modifier-groups/{group_id}/products", headers=pos_auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == str(test_product.id)
    assert data[0]["ref"] == test_product.ref
    assert data[0]["is_active"] is True


# ── Auth failure ──────────────────────────────────────────────────────────────


async def test_list_product_modifiers_no_token_returns_403(client, test_product):
    """GET /products/{id}/modifiers without a token returns 403."""
    resp = await client.get(f"/products/{test_product.id}/modifiers")
    assert resp.status_code == 403


# ── Invalid input ─────────────────────────────────────────────────────────────


async def test_reorder_product_modifiers_malformed_body_returns_422(
    client, pos_auth_headers, test_product
):
    """PATCH .../modifiers/reorder with a non-UUID id returns 422."""
    resp = await client.patch(
        f"/products/{test_product.id}/modifiers/reorder",
        json={"modifier_group_ids": ["not-a-uuid"]},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 422


async def test_reorder_product_modifiers_duplicate_ids_returns_400(
    client, pos_auth_headers, test_product
):
    """PATCH .../modifiers/reorder rejects a list containing the same id twice."""
    group_a = await _create_group(client, pos_auth_headers, "Group A")

    resp = await client.patch(
        f"/products/{test_product.id}/modifiers/reorder",
        json={"modifier_group_ids": [group_a, group_a]},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 400


# ── Business rule violation ───────────────────────────────────────────────────


async def test_reorder_product_modifiers_wrong_brand_group_returns_400(
    client, db, pos_auth_headers, test_product, test_group
):
    """A modifier_group_id belonging to a different brand is rejected with 400."""
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
    other_group = ModifierGroup(
        id=uuid.uuid4(),
        brand_id=other_brand.id,
        name="Foreign Group",
        min_selections=0,
        max_selections=1,
        is_active=True,
    )
    db.add(other_group)
    await db.commit()

    resp = await client.patch(
        f"/products/{test_product.id}/modifiers/reorder",
        json={"modifier_group_ids": [str(other_group.id)]},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 400


async def test_list_product_modifiers_detailed_returns_options(
    client, pos_auth_headers, test_product
):
    """GET /products/{id}/modifiers/detailed nests each attached group's active options."""
    group_id = await _create_group(client, pos_auth_headers, "Milk", max_selections=1)
    opt_resp = await client.post(
        f"/modifier-groups/{group_id}/options",
        json={"name": "Oat", "price_delta_cents": 70},
        headers=pos_auth_headers,
    )
    assert opt_resp.status_code == 201
    option_id = opt_resp.json()["id"]

    link_resp = await client.post(
        f"/products/{test_product.id}/modifiers",
        json={"modifier_group_id": group_id, "display_order": 0},
        headers=pos_auth_headers,
    )
    assert link_resp.status_code == 201

    resp = await client.get(
        f"/products/{test_product.id}/modifiers/detailed", headers=pos_auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == group_id
    assert data[0]["name"] == "Milk"
    assert data[0]["max_selections"] == 1
    assert data[0]["display_order"] == 0
    assert len(data[0]["options"]) == 1
    assert data[0]["options"][0]["id"] == option_id
    assert data[0]["options"][0]["price_delta_cents"] == 70


async def test_list_product_modifiers_detailed_excludes_unattached_groups(
    client, pos_auth_headers, test_product
):
    """GET /products/{id}/modifiers/detailed omits groups not linked to the product."""
    await _create_group(client, pos_auth_headers, "Unattached")

    resp = await client.get(
        f"/products/{test_product.id}/modifiers/detailed", headers=pos_auth_headers
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_product_modifiers_detailed_excludes_inactive_options(
    client, pos_auth_headers, test_product
):
    """GET /products/{id}/modifiers/detailed omits soft-deleted options from a group."""
    group_id = await _create_group(client, pos_auth_headers, "Extras", max_selections=3)
    opt_resp = await client.post(
        f"/modifier-groups/{group_id}/options",
        json={"name": "Extra shot", "price_delta_cents": 60},
        headers=pos_auth_headers,
    )
    option_id = opt_resp.json()["id"]
    await client.post(
        f"/products/{test_product.id}/modifiers",
        json={"modifier_group_id": group_id, "display_order": 0},
        headers=pos_auth_headers,
    )

    delete_resp = await client.delete(f"/modifier-options/{option_id}", headers=pos_auth_headers)
    assert delete_resp.status_code == 204

    resp = await client.get(
        f"/products/{test_product.id}/modifiers/detailed", headers=pos_auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()[0]["options"] == []


async def test_list_product_modifiers_detailed_unknown_product_returns_404(
    client, pos_auth_headers
):
    """GET /products/{id}/modifiers/detailed for an unknown product returns 404."""
    resp = await client.get(
        f"/products/{uuid.uuid4()}/modifiers/detailed", headers=pos_auth_headers
    )
    assert resp.status_code == 404


async def test_list_product_modifiers_detailed_no_token_returns_403(client, test_product):
    """GET /products/{id}/modifiers/detailed without a token returns 403."""
    resp = await client.get(f"/products/{test_product.id}/modifiers/detailed")
    assert resp.status_code == 403


async def test_list_modifier_group_products_wrong_brand_returns_404(
    client, db, pos_auth_headers, test_group
):
    """GET /modifier-groups/{id}/products for a group in another brand returns 404."""
    other_brand = Brand(
        id=uuid.uuid4(),
        group_id=test_group.id,
        name="Other Brand 2",
        is_active=True,
        timezone="Australia/Sydney",
        currency="AUD",
        country="AU",
    )
    db.add(other_brand)
    await db.flush()
    other_group = ModifierGroup(
        id=uuid.uuid4(),
        brand_id=other_brand.id,
        name="Foreign Group 2",
        min_selections=0,
        max_selections=1,
        is_active=True,
    )
    db.add(other_group)
    await db.commit()

    resp = await client.get(f"/modifier-groups/{other_group.id}/products", headers=pos_auth_headers)
    assert resp.status_code == 404
