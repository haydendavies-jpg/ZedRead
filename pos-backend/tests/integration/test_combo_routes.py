"""Integration tests for combo routes.

Covers combo group creation, option add/remove, circular reference rejection,
duplicate option rejection, and audit log assertions.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.product import Product


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _create_extra_product(client: AsyncClient, headers: dict, brand_id, category_id) -> str:
    """Create a second product and return its ID string."""
    resp = await client.post(
        "/products",
        json={
            "category_id": str(category_id),
            "name": "Side Salad",
            "base_price_cents": 500,
            "display_order": 1,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_combo_group_happy_path(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
) -> None:
    """POST /products/{id}/combos/groups returns 201 and the new combo group."""
    resp = await client.post(
        f"/products/{test_product.id}/combos/groups",
        json={
            "name": "Choose a Side",
            "min_selections": 1,
            "max_selections": 1,
            "is_required": True,
            "display_order": 0,
        },
        headers=pos_auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Choose a Side"
    assert data["product_id"] == str(test_product.id)
    assert data["is_required"] is True


@pytest.mark.asyncio
async def test_create_combo_group_writes_audit_log(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    db: AsyncSession,
) -> None:
    """Creating a combo group writes a 'combo_group.created' audit row."""
    await client.post(
        f"/products/{test_product.id}/combos/groups",
        json={"name": "Drink Choice", "min_selections": 1, "max_selections": 1},
        headers=pos_auth_headers,
    )
    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "combo_group.created")
    )
    log = result.scalar_one_or_none()
    assert log is not None


@pytest.mark.asyncio
async def test_add_combo_option_happy_path(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    test_brand,
    test_site,
) -> None:
    """POST /products/{id}/combos/groups/{gid}/options returns 201 with the option."""
    # Create a combo group on test_product
    group_resp = await client.post(
        f"/products/{test_product.id}/combos/groups",
        json={"name": "Sides", "min_selections": 1, "max_selections": 1},
        headers=pos_auth_headers,
    )
    assert group_resp.status_code == 201
    group_id = group_resp.json()["id"]

    # Create a second product to be the option
    # Get a category_id from test_product via the list endpoint
    prod_resp = await client.get(f"/products/{test_product.id}", headers=pos_auth_headers)
    category_id = prod_resp.json()["category_id"]
    option_product_id = await _create_extra_product(
        client, pos_auth_headers, test_brand.id, category_id
    )

    opt_resp = await client.post(
        f"/products/{test_product.id}/combos/groups/{group_id}/options",
        json={"product_id": option_product_id, "price_delta_cents": 0},
        headers=pos_auth_headers,
    )
    assert opt_resp.status_code == 201
    data = opt_resp.json()
    assert data["product_id"] == option_product_id
    assert data["combo_group_id"] == group_id


@pytest.mark.asyncio
async def test_add_combo_option_self_reference_returns_400(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
) -> None:
    """Adding a product as an option of itself returns 400."""
    group_resp = await client.post(
        f"/products/{test_product.id}/combos/groups",
        json={"name": "Self Loop", "min_selections": 1, "max_selections": 1},
        headers=pos_auth_headers,
    )
    assert group_resp.status_code == 201
    group_id = group_resp.json()["id"]

    opt_resp = await client.post(
        f"/products/{test_product.id}/combos/groups/{group_id}/options",
        json={"product_id": str(test_product.id), "price_delta_cents": 0},
        headers=pos_auth_headers,
    )
    assert opt_resp.status_code == 400


@pytest.mark.asyncio
async def test_add_combo_option_duplicate_returns_409(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    test_brand,
) -> None:
    """Adding the same product as an option twice in the same group returns 409."""
    group_resp = await client.post(
        f"/products/{test_product.id}/combos/groups",
        json={"name": "Sides", "min_selections": 1, "max_selections": 2},
        headers=pos_auth_headers,
    )
    assert group_resp.status_code == 201
    group_id = group_resp.json()["id"]

    prod_resp = await client.get(f"/products/{test_product.id}", headers=pos_auth_headers)
    category_id = prod_resp.json()["category_id"]
    option_product_id = await _create_extra_product(
        client, pos_auth_headers, test_brand.id, category_id
    )

    payload = {"product_id": option_product_id, "price_delta_cents": 0}
    r1 = await client.post(
        f"/products/{test_product.id}/combos/groups/{group_id}/options",
        json=payload,
        headers=pos_auth_headers,
    )
    assert r1.status_code == 201

    r2 = await client.post(
        f"/products/{test_product.id}/combos/groups/{group_id}/options",
        json=payload,
        headers=pos_auth_headers,
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_circular_combo_reference_returns_400(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    test_brand,
) -> None:
    """Adding an option that creates a circular chain (A→B→A) returns 400."""
    # Create Product B
    prod_a_resp = await client.get(f"/products/{test_product.id}", headers=pos_auth_headers)
    category_id = prod_a_resp.json()["category_id"]

    # Product B
    resp_b = await client.post(
        "/products",
        json={
            "category_id": category_id,
            "name": "Product B",
            "base_price_cents": 800,
            "display_order": 2,
        },
        headers=pos_auth_headers,
    )
    assert resp_b.status_code == 201
    product_b_id = resp_b.json()["id"]

    # Product A → has combo group with option = Product B
    group_a_resp = await client.post(
        f"/products/{test_product.id}/combos/groups",
        json={"name": "A's group", "min_selections": 1, "max_selections": 1},
        headers=pos_auth_headers,
    )
    group_a_id = group_a_resp.json()["id"]

    opt_resp = await client.post(
        f"/products/{test_product.id}/combos/groups/{group_a_id}/options",
        json={"product_id": product_b_id, "price_delta_cents": 0},
        headers=pos_auth_headers,
    )
    assert opt_resp.status_code == 201

    # Product B → has combo group with option = Product A (circular!)
    group_b_resp = await client.post(
        f"/products/{product_b_id}/combos/groups",
        json={"name": "B's group", "min_selections": 1, "max_selections": 1},
        headers=pos_auth_headers,
    )
    group_b_id = group_b_resp.json()["id"]

    circular_resp = await client.post(
        f"/products/{product_b_id}/combos/groups/{group_b_id}/options",
        json={"product_id": str(test_product.id), "price_delta_cents": 0},
        headers=pos_auth_headers,
    )
    assert circular_resp.status_code == 400


@pytest.mark.asyncio
async def test_remove_combo_option(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    test_brand,
) -> None:
    """DELETE /products/{id}/combos/groups/{gid}/options/{oid} returns 204."""
    group_resp = await client.post(
        f"/products/{test_product.id}/combos/groups",
        json={"name": "Drinks", "min_selections": 1, "max_selections": 1},
        headers=pos_auth_headers,
    )
    group_id = group_resp.json()["id"]

    prod_resp = await client.get(f"/products/{test_product.id}", headers=pos_auth_headers)
    category_id = prod_resp.json()["category_id"]
    option_product_id = await _create_extra_product(
        client, pos_auth_headers, test_brand.id, category_id
    )

    add_resp = await client.post(
        f"/products/{test_product.id}/combos/groups/{group_id}/options",
        json={"product_id": option_product_id, "price_delta_cents": 0},
        headers=pos_auth_headers,
    )
    assert add_resp.status_code == 201
    option_id = add_resp.json()["id"]

    del_resp = await client.delete(
        f"/products/{test_product.id}/combos/groups/{group_id}/options/{option_id}",
        headers=pos_auth_headers,
    )
    assert del_resp.status_code == 204
