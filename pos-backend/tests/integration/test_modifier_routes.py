"""Integration tests for modifier routes.

Covers modifier group CRUD, modifier option CRUD, product–modifier link/unlink,
and audit log assertions.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


@pytest.mark.asyncio
async def test_create_modifier_group_happy_path(
    client: AsyncClient,
    pos_auth_headers: dict,
) -> None:
    """POST /modifier-groups returns 201 and the new group."""
    resp = await client.post(
        "/modifier-groups",
        json={"name": "Sauces", "min_selections": 0, "max_selections": 3},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Sauces"
    assert data["max_selections"] == 3
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_modifier_group_writes_audit_log(
    client: AsyncClient,
    pos_auth_headers: dict,
    db: AsyncSession,
) -> None:
    """Creating a modifier group writes a 'modifier_group.created' audit row."""
    await client.post(
        "/modifier-groups",
        json={"name": "Drinks", "min_selections": 1, "max_selections": 1},
        headers=pos_auth_headers,
    )
    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "modifier_group.created")
    )
    log = result.scalar_one_or_none()
    assert log is not None


@pytest.mark.asyncio
async def test_update_modifier_group(
    client: AsyncClient,
    pos_auth_headers: dict,
) -> None:
    """PATCH /modifier-groups/{id} updates name and max_selections."""
    create_resp = await client.post(
        "/modifier-groups",
        json={"name": "Toppings", "min_selections": 0, "max_selections": 2},
        headers=pos_auth_headers,
    )
    assert create_resp.status_code == 201
    group_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/modifier-groups/{group_id}",
        json={"name": "Extra Toppings", "max_selections": 5},
        headers=pos_auth_headers,
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["name"] == "Extra Toppings"
    assert data["max_selections"] == 5


@pytest.mark.asyncio
async def test_create_modifier_group_defaults_has_quantity_false(
    client: AsyncClient,
    pos_auth_headers: dict,
) -> None:
    """POST /modifier-groups without has_quantity defaults it to False (once-per-option)."""
    resp = await client.post(
        "/modifier-groups",
        json={"name": "Syrups", "min_selections": 0, "max_selections": 3},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["has_quantity"] is False


@pytest.mark.asyncio
async def test_update_modifier_group_has_quantity(
    client: AsyncClient,
    pos_auth_headers: dict,
    db: AsyncSession,
) -> None:
    """PATCH /modifier-groups/{id} toggles has_quantity and writes the audit row with it."""
    create_resp = await client.post(
        "/modifier-groups",
        json={"name": "Shots", "min_selections": 0, "max_selections": 4},
        headers=pos_auth_headers,
    )
    group_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/modifier-groups/{group_id}",
        json={"has_quantity": True},
        headers=pos_auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["has_quantity"] is True

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.action == "modifier_group.updated",
            AuditLog.entity_id == group_id,
        )
    )
    log = result.scalar_one()
    assert log.after_state["has_quantity"] is True
    assert log.before_state["has_quantity"] is False


@pytest.mark.asyncio
async def test_duplicate_modifier_group_copies_has_quantity(
    client: AsyncClient,
    pos_auth_headers: dict,
) -> None:
    """POST /modifier-groups/{id}/duplicate carries the source group's has_quantity across."""
    create_resp = await client.post(
        "/modifier-groups",
        json={"name": "Extras", "min_selections": 0, "max_selections": 5, "has_quantity": True},
        headers=pos_auth_headers,
    )
    group_id = create_resp.json()["id"]
    assert create_resp.json()["has_quantity"] is True

    dup_resp = await client.post(f"/modifier-groups/{group_id}/duplicate", headers=pos_auth_headers)
    assert dup_resp.status_code == 201
    assert dup_resp.json()["has_quantity"] is True


@pytest.mark.asyncio
async def test_create_modifier_group_defaults_first_option_not_selected(
    client: AsyncClient,
    pos_auth_headers: dict,
) -> None:
    """POST /modifier-groups without is_first_option_default_selected defaults it to False."""
    resp = await client.post(
        "/modifier-groups",
        json={"name": "Ice Levels", "min_selections": 0, "max_selections": 1},
        headers=pos_auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["is_first_option_default_selected"] is False


@pytest.mark.asyncio
async def test_update_modifier_group_is_first_option_default_selected(
    client: AsyncClient,
    pos_auth_headers: dict,
    db: AsyncSession,
) -> None:
    """PATCH /modifier-groups/{id} toggles is_first_option_default_selected and writes the audit row with it."""
    create_resp = await client.post(
        "/modifier-groups",
        json={"name": "Milk", "min_selections": 0, "max_selections": 1},
        headers=pos_auth_headers,
    )
    group_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/modifier-groups/{group_id}",
        json={"is_first_option_default_selected": True},
        headers=pos_auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_first_option_default_selected"] is True

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.action == "modifier_group.updated",
            AuditLog.entity_id == group_id,
        )
    )
    log = result.scalar_one()
    assert log.after_state["is_first_option_default_selected"] is True
    assert log.before_state["is_first_option_default_selected"] is False


@pytest.mark.asyncio
async def test_duplicate_modifier_group_copies_first_option_default_selected(
    client: AsyncClient,
    pos_auth_headers: dict,
) -> None:
    """POST /modifier-groups/{id}/duplicate carries the source group's is_first_option_default_selected across."""
    create_resp = await client.post(
        "/modifier-groups",
        json={
            "name": "Size",
            "min_selections": 1,
            "max_selections": 1,
            "is_first_option_default_selected": True,
        },
        headers=pos_auth_headers,
    )
    group_id = create_resp.json()["id"]
    assert create_resp.json()["is_first_option_default_selected"] is True

    dup_resp = await client.post(f"/modifier-groups/{group_id}/duplicate", headers=pos_auth_headers)
    assert dup_resp.status_code == 201
    assert dup_resp.json()["is_first_option_default_selected"] is True


@pytest.mark.asyncio
async def test_create_modifier_option_happy_path(
    client: AsyncClient,
    pos_auth_headers: dict,
) -> None:
    """POST /modifier-groups/{id}/options returns 201 and the new option."""
    create_resp = await client.post(
        "/modifier-groups",
        json={"name": "Extras", "min_selections": 0, "max_selections": 3},
        headers=pos_auth_headers,
    )
    assert create_resp.status_code == 201
    group_id = create_resp.json()["id"]

    opt_resp = await client.post(
        f"/modifier-groups/{group_id}/options",
        json={"name": "Extra Cheese", "price_delta_cents": 50, "display_order": 0},
        headers=pos_auth_headers,
    )
    assert opt_resp.status_code == 201
    data = opt_resp.json()
    assert data["name"] == "Extra Cheese"
    assert data["price_delta_cents"] == 50


@pytest.mark.asyncio
async def test_link_modifier_group_to_product(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
) -> None:
    """POST /products/{id}/modifiers links a modifier group to a product."""
    create_resp = await client.post(
        "/modifier-groups",
        json={"name": "Sauces", "min_selections": 0, "max_selections": 2},
        headers=pos_auth_headers,
    )
    assert create_resp.status_code == 201
    group_id = create_resp.json()["id"]

    link_resp = await client.post(
        f"/products/{test_product.id}/modifiers",
        json={"modifier_group_id": group_id, "display_order": 0},
        headers=pos_auth_headers,
    )
    assert link_resp.status_code == 201
    data = link_resp.json()
    assert data["modifier_group_id"] == group_id
    assert data["product_id"] == str(test_product.id)


@pytest.mark.asyncio
async def test_link_modifier_group_duplicate_returns_409(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
) -> None:
    """Linking the same modifier group to the same product twice returns 409."""
    create_resp = await client.post(
        "/modifier-groups",
        json={"name": "Drinks", "min_selections": 1, "max_selections": 1},
        headers=pos_auth_headers,
    )
    assert create_resp.status_code == 201
    group_id = create_resp.json()["id"]

    payload = {"modifier_group_id": group_id, "display_order": 0}
    r1 = await client.post(
        f"/products/{test_product.id}/modifiers", json=payload, headers=pos_auth_headers
    )
    assert r1.status_code == 201

    r2 = await client.post(
        f"/products/{test_product.id}/modifiers", json=payload, headers=pos_auth_headers
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_unlink_modifier_group_from_product(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
) -> None:
    """DELETE /products/{id}/modifiers/{group_id} removes the link and returns 204."""
    create_resp = await client.post(
        "/modifier-groups",
        json={"name": "Sides", "min_selections": 0, "max_selections": 1},
        headers=pos_auth_headers,
    )
    assert create_resp.status_code == 201
    group_id = create_resp.json()["id"]

    link_resp = await client.post(
        f"/products/{test_product.id}/modifiers",
        json={"modifier_group_id": group_id, "display_order": 0},
        headers=pos_auth_headers,
    )
    assert link_resp.status_code == 201

    unlink_resp = await client.delete(
        f"/products/{test_product.id}/modifiers/{group_id}",
        headers=pos_auth_headers,
    )
    assert unlink_resp.status_code == 204


@pytest.mark.asyncio
async def test_update_modifier_option_writes_audit_log(
    client: AsyncClient,
    pos_auth_headers: dict,
    db: AsyncSession,
) -> None:
    """Updating a modifier option writes a 'modifier_option.updated' audit row."""
    group_resp = await client.post(
        "/modifier-groups",
        json={"name": "Proteins", "min_selections": 1, "max_selections": 1},
        headers=pos_auth_headers,
    )
    group_id = group_resp.json()["id"]

    opt_resp = await client.post(
        f"/modifier-groups/{group_id}/options",
        json={"name": "Chicken", "price_delta_cents": 0},
        headers=pos_auth_headers,
    )
    option_id = opt_resp.json()["id"]

    await client.patch(
        f"/modifier-options/{option_id}",
        json={"name": "Grilled Chicken", "price_delta_cents": 100},
        headers=pos_auth_headers,
    )

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "modifier_option.updated")
    )
    log = result.scalar_one_or_none()
    assert log is not None
