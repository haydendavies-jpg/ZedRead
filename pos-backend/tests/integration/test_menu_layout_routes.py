"""Integration tests for POS Menu Builder routes (Stage 23).

Covers:
1. Happy path — create/list/detail a layout, add tabs/buttons, reorder, rename, delete
2. Auth failure — no token returns 401; POS terminal token returns 403 on writes
3. Invalid input — missing site_id for scope='site' returns 400/422
4. Business rules — foreign brand site rejected, unknown/inactive product_ref rejected,
   publish warns (not fails) on a stale ref, site-scoped POS contract only returns
   layouts visible to that site
5. Audit log — MENU_LAYOUT_CREATED, MENU_TAB_CREATED, MENU_BUTTON_ADDED, MENU_LAYOUT_PUBLISHED
"""

import uuid

import pytest
from sqlalchemy import select

from app.constants.audit_actions import (
    MENU_BUTTON_ADDED,
    MENU_LAYOUT_CREATED,
    MENU_LAYOUT_PUBLISHED,
    MENU_LAYOUT_UPDATED,
    MENU_TAB_CREATED,
)
from app.models.audit_log import AuditLog

pytestmark = pytest.mark.asyncio


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_create_brand_scope_layout_returns_201(client, mgmt_auth_headers, test_brand):
    """POST /menu-layouts creates a brand-wide layout."""
    response = await client.post(
        "/menu-layouts",
        json={"name": "Main Menu", "scope": "brand"},
        headers=mgmt_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Main Menu"
    assert body["scope"] == "brand"
    assert body["site_id"] is None
    assert body["is_published"] is False
    assert body["version"] == 1


async def test_create_site_scope_layout_returns_201(client, mgmt_auth_headers, test_site):
    """POST /menu-layouts creates a site-specific layout."""
    response = await client.post(
        "/menu-layouts",
        json={"name": "Breakfast Menu", "scope": "site", "site_id": str(test_site.id)},
        headers=mgmt_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["scope"] == "site"
    assert body["site_id"] == str(test_site.id)


async def test_create_menu_layout_writes_audit_log(client, db, mgmt_auth_headers, test_user):
    """Creating a layout writes a MENU_LAYOUT_CREATED audit row."""
    await client.post("/menu-layouts", json={"name": "Lunch Menu", "scope": "brand"}, headers=mgmt_auth_headers)

    result = await db.execute(select(AuditLog).where(AuditLog.action == MENU_LAYOUT_CREATED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_list_menu_layouts_includes_created(client, mgmt_auth_headers):
    """GET /menu-layouts lists layouts for the brand."""
    await client.post("/menu-layouts", json={"name": "Dinner Menu", "scope": "brand"}, headers=mgmt_auth_headers)

    response = await client.get("/menu-layouts", headers=mgmt_auth_headers)
    assert response.status_code == 200
    names = [layout["name"] for layout in response.json()]
    assert "Dinner Menu" in names


async def test_get_menu_layout_detail_includes_empty_tabs(client, mgmt_auth_headers):
    """GET /menu-layouts/{id} returns tabs=[] for a fresh layout."""
    create_resp = await client.post(
        "/menu-layouts", json={"name": "Detail Menu", "scope": "brand"}, headers=mgmt_auth_headers
    )
    layout_id = create_resp.json()["id"]

    response = await client.get(f"/menu-layouts/{layout_id}", headers=mgmt_auth_headers)
    assert response.status_code == 200
    assert response.json()["tabs"] == []


async def test_rename_menu_layout(client, mgmt_auth_headers):
    """PATCH /menu-layouts/{id} renames a layout."""
    create_resp = await client.post(
        "/menu-layouts", json={"name": "Old Name", "scope": "brand"}, headers=mgmt_auth_headers
    )
    layout_id = create_resp.json()["id"]

    response = await client.patch(f"/menu-layouts/{layout_id}", json={"name": "New Name"}, headers=mgmt_auth_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


async def test_delete_menu_layout(client, mgmt_auth_headers):
    """DELETE /menu-layouts/{id} removes the layout."""
    create_resp = await client.post(
        "/menu-layouts", json={"name": "To Delete", "scope": "brand"}, headers=mgmt_auth_headers
    )
    layout_id = create_resp.json()["id"]

    response = await client.delete(f"/menu-layouts/{layout_id}", headers=mgmt_auth_headers)
    assert response.status_code == 204

    get_resp = await client.get(f"/menu-layouts/{layout_id}", headers=mgmt_auth_headers)
    assert get_resp.status_code == 404


# ── Tabs ──────────────────────────────────────────────────────────────────────


async def _create_layout(client, headers, name="Test Layout"):
    resp = await client.post("/menu-layouts", json={"name": name, "scope": "brand"}, headers=headers)
    return resp.json()["id"]


async def test_create_tab_returns_201(client, mgmt_auth_headers):
    """POST /menu-layouts/{id}/tabs adds a tab with an empty button list."""
    layout_id = await _create_layout(client, mgmt_auth_headers)

    response = await client.post(f"/menu-layouts/{layout_id}/tabs", json={"name": "Burgers"}, headers=mgmt_auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Burgers"
    assert body["buttons"] == []


async def test_create_tab_writes_audit_log(client, db, mgmt_auth_headers, test_user):
    """Adding a tab writes a MENU_TAB_CREATED audit row."""
    layout_id = await _create_layout(client, mgmt_auth_headers)
    await client.post(f"/menu-layouts/{layout_id}/tabs", json={"name": "Drinks"}, headers=mgmt_auth_headers)

    result = await db.execute(select(AuditLog).where(AuditLog.action == MENU_TAB_CREATED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_rename_tab(client, mgmt_auth_headers):
    """PATCH /menu-layouts/{id}/tabs/{tab_id} renames a tab."""
    layout_id = await _create_layout(client, mgmt_auth_headers)
    tab_resp = await client.post(f"/menu-layouts/{layout_id}/tabs", json={"name": "Old"}, headers=mgmt_auth_headers)
    tab_id = tab_resp.json()["id"]

    response = await client.patch(
        f"/menu-layouts/{layout_id}/tabs/{tab_id}", json={"name": "New"}, headers=mgmt_auth_headers
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New"


async def test_reorder_tabs(client, mgmt_auth_headers):
    """POST /menu-layouts/{id}/tabs/reorder sets display_order to list index."""
    layout_id = await _create_layout(client, mgmt_auth_headers)
    tab_a = (await client.post(f"/menu-layouts/{layout_id}/tabs", json={"name": "A"}, headers=mgmt_auth_headers)).json()
    tab_b = (await client.post(f"/menu-layouts/{layout_id}/tabs", json={"name": "B"}, headers=mgmt_auth_headers)).json()

    response = await client.post(
        f"/menu-layouts/{layout_id}/tabs/reorder",
        json={"tab_ids": [tab_b["id"], tab_a["id"]]},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body[0]["id"] == tab_b["id"]
    assert body[0]["display_order"] == 0
    assert body[1]["id"] == tab_a["id"]
    assert body[1]["display_order"] == 1


async def test_delete_tab(client, mgmt_auth_headers):
    """DELETE /menu-layouts/{id}/tabs/{tab_id} removes the tab."""
    layout_id = await _create_layout(client, mgmt_auth_headers)
    tab_resp = await client.post(f"/menu-layouts/{layout_id}/tabs", json={"name": "Gone"}, headers=mgmt_auth_headers)
    tab_id = tab_resp.json()["id"]

    response = await client.delete(f"/menu-layouts/{layout_id}/tabs/{tab_id}", headers=mgmt_auth_headers)
    assert response.status_code == 204

    detail = await client.get(f"/menu-layouts/{layout_id}", headers=mgmt_auth_headers)
    assert detail.json()["tabs"] == []


# ── Buttons ───────────────────────────────────────────────────────────────────


async def _create_layout_with_tab(client, headers, layout_name="Layout", tab_name="Tab"):
    layout_id = await _create_layout(client, headers, layout_name)
    tab_resp = await client.post(f"/menu-layouts/{layout_id}/tabs", json={"name": tab_name}, headers=headers)
    return layout_id, tab_resp.json()["id"]


async def test_create_button_resolves_product(client, mgmt_auth_headers, test_product):
    """POST .../buttons resolves product_name/price_cents/is_active from the ref."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers)

    response = await client.post(
        f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons",
        json={"product_ref": test_product.ref},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["product_ref"] == test_product.ref
    assert body["product_name"] == test_product.name
    assert body["price_cents"] == test_product.base_price_cents
    assert body["is_active"] is True


async def test_create_button_writes_audit_log(client, db, mgmt_auth_headers, test_user, test_product):
    """Adding a button writes a MENU_BUTTON_ADDED audit row."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers)
    await client.post(
        f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons",
        json={"product_ref": test_product.ref},
        headers=mgmt_auth_headers,
    )

    result = await db.execute(select(AuditLog).where(AuditLog.action == MENU_BUTTON_ADDED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_create_button_unknown_ref_returns_400(client, mgmt_auth_headers):
    """POST .../buttons with a ref that resolves to no product returns 400."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers)

    response = await client.post(
        f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons",
        json={"product_ref": "PRD-999999"},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 400


async def test_reorder_buttons_moves_across_tabs(client, mgmt_auth_headers, test_product):
    """POST .../buttons/reorder moves a button into the destination tab."""
    layout_id, tab_a = await _create_layout_with_tab(client, mgmt_auth_headers, tab_name="A")
    tab_b = (
        await client.post(f"/menu-layouts/{layout_id}/tabs", json={"name": "B"}, headers=mgmt_auth_headers)
    ).json()["id"]

    button_resp = await client.post(
        f"/menu-layouts/{layout_id}/tabs/{tab_a}/buttons",
        json={"product_ref": test_product.ref},
        headers=mgmt_auth_headers,
    )
    button_id = button_resp.json()["id"]

    response = await client.post(
        f"/menu-layouts/{layout_id}/tabs/{tab_b}/buttons/reorder",
        json={"button_ids": [button_id]},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == tab_b
    assert len(body["buttons"]) == 1
    assert body["buttons"][0]["id"] == button_id

    tab_a_detail = next(
        t for t in (await client.get(f"/menu-layouts/{layout_id}", headers=mgmt_auth_headers)).json()["tabs"]
        if t["id"] == tab_a
    )
    assert tab_a_detail["buttons"] == []


async def test_delete_button(client, mgmt_auth_headers, test_product):
    """DELETE .../buttons/{button_id} removes the button."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers)
    button_resp = await client.post(
        f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons",
        json={"product_ref": test_product.ref},
        headers=mgmt_auth_headers,
    )
    button_id = button_resp.json()["id"]

    response = await client.delete(
        f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons/{button_id}", headers=mgmt_auth_headers
    )
    assert response.status_code == 204


# ── Publish ───────────────────────────────────────────────────────────────────


async def test_publish_with_no_warnings(client, mgmt_auth_headers, test_product):
    """POST .../publish with all valid buttons returns no warnings and bumps version."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers)
    await client.post(
        f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons",
        json={"product_ref": test_product.ref},
        headers=mgmt_auth_headers,
    )

    response = await client.post(f"/menu-layouts/{layout_id}/publish", headers=mgmt_auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["layout"]["is_published"] is True
    assert body["layout"]["version"] == 2
    assert body["warnings"] == []


async def test_publish_writes_audit_log(client, db, mgmt_auth_headers, test_user):
    """Publishing a layout writes a MENU_LAYOUT_PUBLISHED audit row."""
    layout_id = await _create_layout(client, mgmt_auth_headers)
    await client.post(f"/menu-layouts/{layout_id}/publish", headers=mgmt_auth_headers)

    result = await db.execute(select(AuditLog).where(AuditLog.action == MENU_LAYOUT_PUBLISHED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_publish_warns_on_deactivated_product(client, db, mgmt_auth_headers, test_product):
    """Publishing warns (not fails) when a button's product has since been deactivated."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers)
    await client.post(
        f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons",
        json={"product_ref": test_product.ref},
        headers=mgmt_auth_headers,
    )

    test_product.is_active = False
    db.add(test_product)
    await db.commit()

    response = await client.post(f"/menu-layouts/{layout_id}/publish", headers=mgmt_auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["layout"]["is_published"] is True
    assert len(body["warnings"]) == 1
    assert body["warnings"][0]["reason"] == "product_inactive"
    assert body["warnings"][0]["product_ref"] == test_product.ref


async def test_unpublish(client, mgmt_auth_headers):
    """POST .../unpublish clears is_published."""
    layout_id = await _create_layout(client, mgmt_auth_headers)
    await client.post(f"/menu-layouts/{layout_id}/publish", headers=mgmt_auth_headers)

    response = await client.post(f"/menu-layouts/{layout_id}/unpublish", headers=mgmt_auth_headers)
    assert response.status_code == 200
    assert response.json()["is_published"] is False


# ── Auth / validation ─────────────────────────────────────────────────────────


async def test_list_menu_layouts_no_token_returns_403(client):
    """GET /menu-layouts with no Authorization header returns 403 (HTTPBearer default)."""
    response = await client.get("/menu-layouts")
    assert response.status_code == 403


async def test_create_menu_layout_pos_token_returns_403(client, pos_auth_headers):
    """POST /menu-layouts with a POS terminal token returns 403."""
    response = await client.post(
        "/menu-layouts", json={"name": "Blocked", "scope": "brand"}, headers=pos_auth_headers
    )
    assert response.status_code == 403


async def test_create_site_scope_layout_missing_site_id_returns_400(client, mgmt_auth_headers):
    """POST /menu-layouts with scope='site' and no site_id returns 400."""
    response = await client.post(
        "/menu-layouts", json={"name": "No Site", "scope": "site"}, headers=mgmt_auth_headers
    )
    assert response.status_code == 400


async def test_create_site_scope_layout_foreign_site_returns_400(client, mgmt_auth_headers):
    """POST /menu-layouts with a site_id that doesn't belong to the brand returns 400."""
    response = await client.post(
        "/menu-layouts",
        json={"name": "Foreign Site", "scope": "site", "site_id": str(uuid.uuid4())},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 400


async def test_create_menu_layout_invalid_scope_returns_422(client, mgmt_auth_headers):
    """POST /menu-layouts with an invalid scope value returns 422."""
    response = await client.post(
        "/menu-layouts", json={"name": "Bad Scope", "scope": "galaxy"}, headers=mgmt_auth_headers
    )
    assert response.status_code == 422


# ── POS consumption contract ──────────────────────────────────────────────────


async def test_pos_menu_layout_returns_published_brand_layout(client, db, pos_auth_headers, test_brand, test_site):
    """
    GET /pos/menu-layout?site_id= returns a published brand-wide layout.

    Layout is seeded directly via the ORM (not the management API) so this
    test only needs pos_auth_headers' grant — combining it with
    mgmt_auth_headers in the same test would create two active
    UserAccessGrant rows for the same (user_id, site_id), which trips the
    (pre-existing, out of scope for this stage) ambiguous-grant lookup in
    resolve_access/resolve_catalog_access's POS branch.
    """
    from app.models.menu_layout import MenuLayout

    layout = MenuLayout(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        site_id=None,
        scope="brand",
        name="Published Brand Menu",
        is_published=True,
        version=2,
    )
    db.add(layout)
    await db.commit()

    response = await client.get(f"/pos/menu-layout?site_id={test_site.id}", headers=pos_auth_headers)
    assert response.status_code == 200
    names = [l["name"] for l in response.json()]
    assert "Published Brand Menu" in names


async def test_pos_menu_layout_excludes_unpublished(client, db, pos_auth_headers, test_brand, test_site):
    """GET /pos/menu-layout excludes layouts that have never been published."""
    from app.models.menu_layout import MenuLayout

    layout = MenuLayout(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        site_id=None,
        scope="brand",
        name="Draft Menu",
        is_published=False,
        version=1,
    )
    db.add(layout)
    await db.commit()

    response = await client.get(f"/pos/menu-layout?site_id={test_site.id}", headers=pos_auth_headers)
    assert response.status_code == 200
    names = [l["name"] for l in response.json()]
    assert "Draft Menu" not in names


async def test_pos_menu_layout_wrong_site_returns_403(client, pos_auth_headers):
    """GET /pos/menu-layout with a site_id other than the POS token's own site returns 403."""
    response = await client.get(f"/pos/menu-layout?site_id={uuid.uuid4()}", headers=pos_auth_headers)
    assert response.status_code == 403


# ── Phase 3 — scheduled default (menu selector) ────────────────────────────────


async def test_pos_menu_layout_marks_site_default_over_brand_default(
    client, db, pos_auth_headers, test_brand, test_site
):
    """A site's own is_default layout wins as is_effective_default over a brand-wide default."""
    from app.models.menu_layout import MenuLayout

    brand_default = MenuLayout(
        id=uuid.uuid4(), brand_id=test_brand.id, site_id=None, scope="brand",
        name="Brand Default", is_published=True, is_default=True,
    )
    site_default = MenuLayout(
        id=uuid.uuid4(), brand_id=test_brand.id, site_id=test_site.id, scope="site",
        name="Site Default", is_published=True, is_default=True,
    )
    db.add_all([brand_default, site_default])
    await db.commit()

    response = await client.get(f"/pos/menu-layout?site_id={test_site.id}", headers=pos_auth_headers)
    assert response.status_code == 200
    by_name = {l["name"]: l for l in response.json()}
    assert by_name["Site Default"]["is_effective_default"] is True
    assert by_name["Brand Default"]["is_effective_default"] is False


async def test_pos_menu_layout_no_default_when_none_marked(client, db, pos_auth_headers, test_brand, test_site):
    """No layout is flagged is_effective_default when nothing is marked is_default."""
    from app.models.menu_layout import MenuLayout

    layout = MenuLayout(
        id=uuid.uuid4(), brand_id=test_brand.id, site_id=None, scope="brand",
        name="Plain Menu", is_published=True,
    )
    db.add(layout)
    await db.commit()

    response = await client.get(f"/pos/menu-layout?site_id={test_site.id}", headers=pos_auth_headers)
    assert response.status_code == 200
    assert all(l["is_effective_default"] is False for l in response.json())


async def test_set_layout_default_clears_other_site_scope_default(client, db, mgmt_auth_headers, test_brand, test_site):
    """PATCH /menu-layouts/{id} with is_default=True clears is_default on other layouts in the same site scope."""
    from app.models.menu_layout import MenuLayout

    first = MenuLayout(
        id=uuid.uuid4(), brand_id=test_brand.id, site_id=test_site.id, scope="site",
        name="Lunch", is_default=True,
    )
    second = MenuLayout(
        id=uuid.uuid4(), brand_id=test_brand.id, site_id=test_site.id, scope="site",
        name="Dinner", is_default=False,
    )
    db.add_all([first, second])
    await db.commit()

    response = await client.patch(
        f"/menu-layouts/{second.id}",
        json={"is_default": True},
        params={"brand_id": str(test_brand.id)},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["is_default"] is True

    await db.refresh(first)
    assert first.is_default is False


async def test_set_layout_default_does_not_clear_other_scope(client, db, mgmt_auth_headers, test_brand, test_site):
    """A site-scope default and a brand-scope default don't clear each other — different scope groupings."""
    from app.models.menu_layout import MenuLayout

    brand_layout = MenuLayout(
        id=uuid.uuid4(), brand_id=test_brand.id, site_id=None, scope="brand",
        name="Brand Menu", is_default=True,
    )
    site_layout = MenuLayout(
        id=uuid.uuid4(), brand_id=test_brand.id, site_id=test_site.id, scope="site",
        name="Site Menu", is_default=False,
    )
    db.add_all([brand_layout, site_layout])
    await db.commit()

    response = await client.patch(
        f"/menu-layouts/{site_layout.id}",
        json={"is_default": True},
        params={"brand_id": str(test_brand.id)},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 200

    await db.refresh(brand_layout)
    assert brand_layout.is_default is True


async def test_set_layout_default_writes_audit_log(client, db, mgmt_auth_headers, test_brand):
    """Setting is_default writes a MENU_LAYOUT_UPDATED audit row with before/after state."""
    from app.models.menu_layout import MenuLayout

    layout = MenuLayout(id=uuid.uuid4(), brand_id=test_brand.id, site_id=None, scope="brand", name="Main")
    db.add(layout)
    await db.commit()

    response = await client.patch(
        f"/menu-layouts/{layout.id}",
        json={"is_default": True},
        params={"brand_id": str(test_brand.id)},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 200

    audit = await db.execute(
        select(AuditLog).where(AuditLog.entity_id == str(layout.id), AuditLog.action == MENU_LAYOUT_UPDATED)
    )
    log_row = audit.scalar_one()
    assert log_row.after_state["is_default"] is True
