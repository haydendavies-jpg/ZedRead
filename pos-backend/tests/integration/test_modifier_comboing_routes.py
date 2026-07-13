"""Integration tests for modifier comboing (linked groups), deactivation, and duplication.

Covers:
1. Happy path — link/unlink a group to an option, detailed nested listing,
   duplicate a group, deactivate a group/option
2. Auth failure — no token returns 403
3. Invalid input — missing linked_group_id returns 422
4. Business rules — an option cannot link to its own parent group; duplicate links rejected
5. Audit log — MODIFIER_OPTION_GROUP_LINKED, MODIFIER_GROUP_DUPLICATED, MODIFIER_GROUP_DEACTIVATED
"""

import pytest
from sqlalchemy import select

from app.constants.audit_actions import (
    MODIFIER_GROUP_DEACTIVATED,
    MODIFIER_GROUP_DUPLICATED,
    MODIFIER_OPTION_GROUP_LINKED,
)
from app.models.audit_log import AuditLog

pytestmark = pytest.mark.asyncio


async def _create_group_with_option(client, headers, group_name: str, option_name: str) -> tuple[str, str]:
    """Create a modifier group with one option; return (group_id, option_id)."""
    group_resp = await client.post(
        "/modifier-groups", json={"name": group_name, "min_selections": 0, "max_selections": 1}, headers=headers
    )
    group_id = group_resp.json()["id"]
    option_resp = await client.post(
        f"/modifier-groups/{group_id}/options",
        json={"name": option_name, "price_delta_cents": 0},
        headers=headers,
    )
    return group_id, option_resp.json()["id"]


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_link_option_to_group_returns_201(client, pos_auth_headers):
    """POST /modifier-options/{id}/links links an option to another group."""
    combo_group_id, _ = await _create_group_with_option(client, pos_auth_headers, "Sides", "Fries")
    _, option_id = await _create_group_with_option(client, pos_auth_headers, "Meal Deal", "Combo")

    response = await client.post(
        f"/modifier-options/{option_id}/links",
        json={"linked_group_id": combo_group_id},
        headers=pos_auth_headers,
    )
    assert response.status_code == 201


async def test_link_option_to_group_writes_audit_log(client, db, pos_auth_headers, test_user):
    """Linking an option to a group writes a MODIFIER_OPTION_GROUP_LINKED audit row."""
    combo_group_id, _ = await _create_group_with_option(client, pos_auth_headers, "Sauces", "Ketchup")
    _, option_id = await _create_group_with_option(client, pos_auth_headers, "Burger Deal", "Combo")

    await client.post(
        f"/modifier-options/{option_id}/links", json={"linked_group_id": combo_group_id}, headers=pos_auth_headers
    )

    result = await db.execute(select(AuditLog).where(AuditLog.action == MODIFIER_OPTION_GROUP_LINKED))
    assert result.scalar_one().actor_id == test_user.id


async def test_detailed_listing_includes_linked_group(client, pos_auth_headers, test_brand):
    """GET /modifier-groups/detailed nests linked groups under the option that links to them."""
    combo_group_id, _ = await _create_group_with_option(client, pos_auth_headers, "Drinks Side", "Cola")
    parent_group_id, option_id = await _create_group_with_option(client, pos_auth_headers, "Value Meal", "Make it a combo")
    await client.post(
        f"/modifier-options/{option_id}/links", json={"linked_group_id": combo_group_id}, headers=pos_auth_headers
    )

    response = await client.get(
        "/modifier-groups/detailed", params={"brand_id": str(test_brand.id)}, headers=pos_auth_headers
    )
    assert response.status_code == 200
    parent = next(g for g in response.json() if g["id"] == parent_group_id)
    option = next(o for o in parent["options"] if o["id"] == option_id)
    assert len(option["linked_groups"]) == 1
    assert option["linked_groups"][0]["id"] == combo_group_id
    assert option["linked_groups"][0]["options"][0]["name"] == "Cola"


async def test_unlink_option_group_removes_link(client, pos_auth_headers, test_brand):
    """DELETE /modifier-options/{id}/links/{group_id} removes the comboing link."""
    combo_group_id, _ = await _create_group_with_option(client, pos_auth_headers, "Extras Side", "Nuggets")
    _, option_id = await _create_group_with_option(client, pos_auth_headers, "Deal 2", "Combo")
    await client.post(
        f"/modifier-options/{option_id}/links", json={"linked_group_id": combo_group_id}, headers=pos_auth_headers
    )

    unlink_resp = await client.delete(f"/modifier-options/{option_id}/links/{combo_group_id}", headers=pos_auth_headers)
    assert unlink_resp.status_code == 204

    response = await client.get(
        "/modifier-groups/detailed", params={"brand_id": str(test_brand.id)}, headers=pos_auth_headers
    )
    option = next(o for g in response.json() for o in g["options"] if o["id"] == option_id)
    assert option["linked_groups"] == []


async def test_duplicate_modifier_group(client, db, pos_auth_headers, test_user):
    """POST /modifier-groups/{id}/duplicate copies the group and its options."""
    group_id, _ = await _create_group_with_option(client, pos_auth_headers, "Toppings", "Cheese")

    response = await client.post(f"/modifier-groups/{group_id}/duplicate", headers=pos_auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Toppings (copy)"
    assert body["id"] != group_id

    result = await db.execute(select(AuditLog).where(AuditLog.action == MODIFIER_GROUP_DUPLICATED))
    assert result.scalar_one().actor_id == test_user.id


async def test_deactivate_modifier_group(client, db, pos_auth_headers, test_brand, test_user):
    """DELETE /modifier-groups/{id} soft-deletes the group — excluded from later listings."""
    group_id, _ = await _create_group_with_option(client, pos_auth_headers, "Seasonal", "Pumpkin Spice")

    response = await client.delete(f"/modifier-groups/{group_id}", headers=pos_auth_headers)
    assert response.status_code == 204

    list_resp = await client.get("/modifier-groups", params={"brand_id": str(test_brand.id)}, headers=pos_auth_headers)
    assert group_id not in [g["id"] for g in list_resp.json()]

    result = await db.execute(select(AuditLog).where(AuditLog.action == MODIFIER_GROUP_DEACTIVATED))
    assert result.scalar_one().actor_id == test_user.id


# ── Auth failure ─────────────────────────────────────────────────────────────


async def test_link_option_to_group_no_token_returns_403(client):
    """POST /modifier-options/{id}/links with no Authorization header returns 403."""
    import uuid

    response = await client.post(
        f"/modifier-options/{uuid.uuid4()}/links", json={"linked_group_id": str(uuid.uuid4())}
    )
    assert response.status_code == 403


# ── Invalid input ────────────────────────────────────────────────────────────


async def test_link_option_to_group_missing_field_returns_422(client, pos_auth_headers):
    """POST /modifier-options/{id}/links without linked_group_id returns 422."""
    import uuid

    response = await client.post(f"/modifier-options/{uuid.uuid4()}/links", json={}, headers=pos_auth_headers)
    assert response.status_code == 422


# ── Business rules ───────────────────────────────────────────────────────────


async def test_option_cannot_link_to_own_parent_group(client, pos_auth_headers):
    """An option cannot be linked to the group it already belongs to."""
    group_id, option_id = await _create_group_with_option(client, pos_auth_headers, "Self Link", "Weird Option")

    response = await client.post(
        f"/modifier-options/{option_id}/links", json={"linked_group_id": group_id}, headers=pos_auth_headers
    )
    assert response.status_code == 400


async def test_duplicate_link_returns_409(client, pos_auth_headers):
    """Linking the same group to the same option twice returns 409."""
    combo_group_id, _ = await _create_group_with_option(client, pos_auth_headers, "Dup Side", "Onion Rings")
    _, option_id = await _create_group_with_option(client, pos_auth_headers, "Dup Deal", "Combo")

    await client.post(
        f"/modifier-options/{option_id}/links", json={"linked_group_id": combo_group_id}, headers=pos_auth_headers
    )
    response = await client.post(
        f"/modifier-options/{option_id}/links", json={"linked_group_id": combo_group_id}, headers=pos_auth_headers
    )
    assert response.status_code == 409
