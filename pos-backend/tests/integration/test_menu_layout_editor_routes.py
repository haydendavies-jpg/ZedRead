"""Integration tests for the POS Layout grid editor redesign (Menu Studio Phase 2).

Covers what test_menu_layout_routes.py (Stage 23 prototype) doesn't:
1. Happy path — folder buttons + nested tabs, button resize/recolor, duplicate,
   schedule/cancel-schedule publish, bulk recolor/delete/group-into-tab
2. Auth failure — POS terminal token rejected on the new write routes
3. Invalid input — folder button missing name, product_ref on a folder button
4. Business rules — mixed-tab bulk selection rejected, past schedule time rejected,
   active-time window excludes a layout outside its hours from the POS contract
5. Audit log — MENU_BUTTON_UPDATED, MENU_LAYOUT_DUPLICATED, MENU_LAYOUT_SCHEDULED,
   MENU_BUTTON_BULK_RECOLORED, MENU_BUTTON_BULK_REMOVED, MENU_TAB_GROUPED
"""

import uuid
from datetime import datetime, time, timedelta, timezone

import pytest
from sqlalchemy import select

from app.constants.audit_actions import (
    MENU_BUTTON_BULK_RECOLORED,
    MENU_BUTTON_BULK_REMOVED,
    MENU_BUTTON_UPDATED,
    MENU_LAYOUT_DUPLICATED,
    MENU_LAYOUT_SCHEDULED,
    MENU_TAB_GROUPED,
)
from app.models.audit_log import AuditLog

pytestmark = pytest.mark.asyncio


async def _create_layout_with_tab(client, headers, layout_name="Layout", tab_name="Tab"):
    layout_resp = await client.post("/menu-layouts", json={"name": layout_name, "scope": "brand"}, headers=headers)
    layout_id = layout_resp.json()["id"]
    tab_resp = await client.post(f"/menu-layouts/{layout_id}/tabs", json={"name": tab_name}, headers=headers)
    return layout_id, tab_resp.json()["id"]


async def _create_product_button(client, headers, layout_id, tab_id, product_ref, **extra):
    payload = {"kind": "product", "product_ref": product_ref, **extra}
    resp = await client.post(f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons", json=payload, headers=headers)
    return resp.json()


# ── Folder buttons / nested tabs ─────────────────────────────────────────────


async def test_create_folder_button_creates_nested_tab(client, mgmt_auth_headers):
    """POST .../buttons with kind='folder' creates a nested MenuTab and returns its preview."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers)

    response = await client.post(
        f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons",
        json={"kind": "folder", "name": "Combos"},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "folder"
    assert body["child_tab_name"] == "Combos"
    assert body["child_tab_button_count"] == 0
    assert body["child_tab_id"] is not None

    detail = (await client.get(f"/menu-layouts/{layout_id}", headers=mgmt_auth_headers)).json()
    child_tabs = [t for t in detail["tabs"] if t["id"] == body["child_tab_id"]]
    assert len(child_tabs) == 1
    assert child_tabs[0]["parent_tab_id"] == tab_id


async def test_create_folder_button_missing_name_returns_400(client, mgmt_auth_headers):
    """POST .../buttons with kind='folder' and no name returns 400."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers)

    response = await client.post(
        f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons", json={"kind": "folder"}, headers=mgmt_auth_headers
    )
    assert response.status_code == 400


async def test_delete_folder_button_cascades_nested_tab(client, mgmt_auth_headers):
    """Deleting a folder button also deletes its nested child tab."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers)
    button = (
        await client.post(
            f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons",
            json={"kind": "folder", "name": "Sides"},
            headers=mgmt_auth_headers,
        )
    ).json()

    response = await client.delete(
        f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons/{button['id']}", headers=mgmt_auth_headers
    )
    assert response.status_code == 204

    detail = (await client.get(f"/menu-layouts/{layout_id}", headers=mgmt_auth_headers)).json()
    assert all(t["id"] != button["child_tab_id"] for t in detail["tabs"])


# ── Button update (resize/recolor/relink) ────────────────────────────────────


async def test_update_button_resizes_and_recolors(client, db, mgmt_auth_headers, test_user, test_product):
    """PATCH .../buttons/{id} updates width/height/color and writes MENU_BUTTON_UPDATED."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers)
    button = await _create_product_button(client, mgmt_auth_headers, layout_id, tab_id, test_product.ref)

    response = await client.patch(
        f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons/{button['id']}",
        json={"width": 3, "height": 2, "color": "#112233"},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["width"] == 3
    assert body["height"] == 2
    assert body["color"] == "#112233"

    result = await db.execute(select(AuditLog).where(AuditLog.action == MENU_BUTTON_UPDATED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_update_button_explicit_null_color_clears_override(client, mgmt_auth_headers, test_product):
    """PATCH .../buttons/{id} with {"color": null} clears a colour override (inspector's 'Category default' reset)."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers)
    button = await _create_product_button(client, mgmt_auth_headers, layout_id, tab_id, test_product.ref, color="#112233")
    assert button["color"] == "#112233"

    response = await client.patch(
        f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons/{button['id']}",
        json={"color": None},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["color"] is None


async def test_update_button_product_ref_on_folder_returns_400(client, mgmt_auth_headers):
    """PATCH .../buttons/{id} with product_ref on a folder button returns 400."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers)
    button = (
        await client.post(
            f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons",
            json={"kind": "folder", "name": "Extras"},
            headers=mgmt_auth_headers,
        )
    ).json()

    response = await client.patch(
        f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons/{button['id']}",
        json={"product_ref": "PRD-000001"},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 400


async def test_update_button_invalid_width_returns_422(client, mgmt_auth_headers, test_product):
    """PATCH .../buttons/{id} with width outside 1-6 returns 422."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers)
    button = await _create_product_button(client, mgmt_auth_headers, layout_id, tab_id, test_product.ref)

    response = await client.patch(
        f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons/{button['id']}",
        json={"width": 7},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 422


async def test_update_button_pos_token_returns_403(client, pos_auth_headers):
    """PATCH .../buttons/{id} with a POS terminal token returns 403."""
    response = await client.patch(
        f"/menu-layouts/{uuid.uuid4()}/tabs/{uuid.uuid4()}/buttons/{uuid.uuid4()}",
        json={"width": 2},
        headers=pos_auth_headers,
    )
    assert response.status_code == 403


# ── Bulk actions ──────────────────────────────────────────────────────────────


async def test_bulk_recolor_buttons(client, db, mgmt_auth_headers, test_user, test_product):
    """POST .../buttons/bulk-recolor recolors every listed button and writes one audit row."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers)
    b1 = await _create_product_button(client, mgmt_auth_headers, layout_id, tab_id, test_product.ref)
    b2 = (
        await client.post(
            f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons",
            json={"kind": "folder", "name": "Folder"},
            headers=mgmt_auth_headers,
        )
    ).json()

    response = await client.post(
        f"/menu-layouts/{layout_id}/buttons/bulk-recolor",
        json={"button_ids": [b1["id"], b2["id"]], "color": "#ABCDEF"},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 200
    assert set(response.json()) == {b1["id"], b2["id"]}

    detail = (await client.get(f"/menu-layouts/{layout_id}", headers=mgmt_auth_headers)).json()
    tab = next(t for t in detail["tabs"] if t["id"] == tab_id)
    assert {btn["color"] for btn in tab["buttons"]} == {"#ABCDEF"}

    result = await db.execute(select(AuditLog).where(AuditLog.action == MENU_BUTTON_BULK_RECOLORED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_bulk_recolor_mixed_tabs_returns_400(client, mgmt_auth_headers, test_product):
    """POST .../buttons/bulk-recolor with buttons spanning two tabs returns 400."""
    layout_id, tab_a = await _create_layout_with_tab(client, mgmt_auth_headers, tab_name="A")
    tab_b = (await client.post(f"/menu-layouts/{layout_id}/tabs", json={"name": "B"}, headers=mgmt_auth_headers)).json()["id"]
    b1 = await _create_product_button(client, mgmt_auth_headers, layout_id, tab_a, test_product.ref)
    b2 = (
        await client.post(
            f"/menu-layouts/{layout_id}/tabs/{tab_b}/buttons",
            json={"kind": "folder", "name": "Other"},
            headers=mgmt_auth_headers,
        )
    ).json()

    response = await client.post(
        f"/menu-layouts/{layout_id}/buttons/bulk-recolor",
        json={"button_ids": [b1["id"], b2["id"]], "color": "#ABCDEF"},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 400


async def test_bulk_delete_buttons_cascades_folder_tabs(client, db, mgmt_auth_headers, test_user, test_product):
    """POST .../buttons/bulk-delete removes buttons (and any folder's nested tab) and writes one audit row."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers)
    b1 = await _create_product_button(client, mgmt_auth_headers, layout_id, tab_id, test_product.ref)
    b2 = (
        await client.post(
            f"/menu-layouts/{layout_id}/tabs/{tab_id}/buttons",
            json={"kind": "folder", "name": "ToDelete"},
            headers=mgmt_auth_headers,
        )
    ).json()

    response = await client.post(
        f"/menu-layouts/{layout_id}/buttons/bulk-delete",
        json={"button_ids": [b1["id"], b2["id"]]},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 204

    detail = (await client.get(f"/menu-layouts/{layout_id}", headers=mgmt_auth_headers)).json()
    tab = next(t for t in detail["tabs"] if t["id"] == tab_id)
    assert tab["buttons"] == []
    assert all(t["id"] != b2["child_tab_id"] for t in detail["tabs"])

    result = await db.execute(select(AuditLog).where(AuditLog.action == MENU_BUTTON_BULK_REMOVED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_group_buttons_into_tab(client, db, mgmt_auth_headers, test_user, test_product):
    """POST .../buttons/group-into-tab moves buttons into a new nested tab behind a folder button."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers)
    b1 = await _create_product_button(client, mgmt_auth_headers, layout_id, tab_id, test_product.ref)

    response = await client.post(
        f"/menu-layouts/{layout_id}/buttons/group-into-tab",
        json={"button_ids": [b1["id"]], "name": "Grouped"},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 201
    folder = response.json()
    assert folder["kind"] == "folder"
    assert folder["child_tab_name"] == "Grouped"
    assert folder["child_tab_button_count"] == 1

    detail = (await client.get(f"/menu-layouts/{layout_id}", headers=mgmt_auth_headers)).json()
    source_tab = next(t for t in detail["tabs"] if t["id"] == tab_id)
    assert [btn["id"] for btn in source_tab["buttons"]] == [folder["id"]]
    child_tab = next(t for t in detail["tabs"] if t["id"] == folder["child_tab_id"])
    assert [btn["id"] for btn in child_tab["buttons"]] == [b1["id"]]

    result = await db.execute(select(AuditLog).where(AuditLog.action == MENU_TAB_GROUPED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


# ── Duplicate ─────────────────────────────────────────────────────────────────


async def test_duplicate_layout_copies_tabs_and_buttons(client, db, mgmt_auth_headers, test_user, test_product):
    """POST .../duplicate deep-copies the tab tree and buttons, starting unpublished."""
    layout_id, tab_id = await _create_layout_with_tab(client, mgmt_auth_headers, layout_name="Source")
    await _create_product_button(client, mgmt_auth_headers, layout_id, tab_id, test_product.ref)
    await client.post(f"/menu-layouts/{layout_id}/publish", headers=mgmt_auth_headers)

    response = await client.post(f"/menu-layouts/{layout_id}/duplicate", headers=mgmt_auth_headers)
    assert response.status_code == 201
    copy = response.json()
    assert copy["name"] == "Source (copy)"
    assert copy["is_published"] is False
    assert copy["id"] != layout_id

    detail = (await client.get(f"/menu-layouts/{copy['id']}", headers=mgmt_auth_headers)).json()
    assert len(detail["tabs"]) == 1
    assert len(detail["tabs"][0]["buttons"]) == 1
    assert detail["tabs"][0]["buttons"][0]["product_ref"] == test_product.ref

    result = await db.execute(select(AuditLog).where(AuditLog.action == MENU_LAYOUT_DUPLICATED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


# ── Schedule publish ──────────────────────────────────────────────────────────


async def test_schedule_publish(client, db, mgmt_auth_headers, test_user):
    """POST .../schedule-publish sets scheduled_publish_at and writes MENU_LAYOUT_SCHEDULED."""
    layout_resp = await client.post("/menu-layouts", json={"name": "Scheduled", "scope": "brand"}, headers=mgmt_auth_headers)
    layout_id = layout_resp.json()["id"]
    target = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    response = await client.post(
        f"/menu-layouts/{layout_id}/schedule-publish", json={"scheduled_publish_at": target}, headers=mgmt_auth_headers
    )
    assert response.status_code == 200
    assert response.json()["scheduled_publish_at"] is not None

    result = await db.execute(select(AuditLog).where(AuditLog.action == MENU_LAYOUT_SCHEDULED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_schedule_publish_past_time_returns_400(client, mgmt_auth_headers):
    """POST .../schedule-publish with a time in the past returns 400."""
    layout_resp = await client.post("/menu-layouts", json={"name": "PastSchedule", "scope": "brand"}, headers=mgmt_auth_headers)
    layout_id = layout_resp.json()["id"]
    target = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    response = await client.post(
        f"/menu-layouts/{layout_id}/schedule-publish", json={"scheduled_publish_at": target}, headers=mgmt_auth_headers
    )
    assert response.status_code == 400


async def test_cancel_scheduled_publish(client, mgmt_auth_headers):
    """POST .../cancel-schedule-publish clears scheduled_publish_at."""
    layout_resp = await client.post("/menu-layouts", json={"name": "CancelMe", "scope": "brand"}, headers=mgmt_auth_headers)
    layout_id = layout_resp.json()["id"]
    target = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    await client.post(f"/menu-layouts/{layout_id}/schedule-publish", json={"scheduled_publish_at": target}, headers=mgmt_auth_headers)

    response = await client.post(f"/menu-layouts/{layout_id}/cancel-schedule-publish", headers=mgmt_auth_headers)
    assert response.status_code == 200
    assert response.json()["scheduled_publish_at"] is None


# ── Active-time/day-of-week window ───────────────────────────────────────────


async def test_update_layout_active_time_window(client, mgmt_auth_headers):
    """PATCH /menu-layouts/{id} sets is_all_day=False with a start/end time window."""
    layout_resp = await client.post("/menu-layouts", json={"name": "Breakfast", "scope": "brand"}, headers=mgmt_auth_headers)
    layout_id = layout_resp.json()["id"]

    response = await client.patch(
        f"/menu-layouts/{layout_id}",
        json={"is_all_day": False, "start_time": "07:00:00", "end_time": "11:00:00", "active_days": [0, 1, 2, 3, 4]},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_all_day"] is False
    assert body["start_time"] == "07:00:00"
    assert body["end_time"] == "11:00:00"
    assert body["active_days"] == [0, 1, 2, 3, 4]


async def test_update_layout_all_day_false_without_times_returns_400(client, mgmt_auth_headers):
    """PATCH /menu-layouts/{id} with is_all_day=False and no start/end time returns 400."""
    layout_resp = await client.post("/menu-layouts", json={"name": "Bad Window", "scope": "brand"}, headers=mgmt_auth_headers)
    layout_id = layout_resp.json()["id"]

    response = await client.patch(
        f"/menu-layouts/{layout_id}", json={"is_all_day": False}, headers=mgmt_auth_headers
    )
    assert response.status_code == 400


async def test_pos_menu_layout_excludes_layout_outside_active_window(client, db, pos_auth_headers, test_brand, test_site):
    """GET /pos/menu-layout excludes a published layout whose active-time window doesn't include now."""
    from app.models.menu_layout import MenuLayout

    now = datetime.now(timezone.utc)
    # A window guaranteed not to include "now" — 1 minute long, an hour ago.
    excluded_start = (now - timedelta(hours=1)).time()
    excluded_end = (now - timedelta(hours=1) + timedelta(minutes=1)).time()

    layout = MenuLayout(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        site_id=None,
        scope="brand",
        name="Outside Window Menu",
        is_published=True,
        version=2,
        is_all_day=False,
        start_time=excluded_start,
        end_time=excluded_end,
        active_days=[0, 1, 2, 3, 4, 5, 6],
    )
    db.add(layout)
    await db.commit()

    response = await client.get(f"/pos/menu-layout?site_id={test_site.id}", headers=pos_auth_headers)
    assert response.status_code == 200
    names = [l["name"] for l in response.json()]
    assert "Outside Window Menu" not in names


async def test_pos_menu_layout_includes_layout_inside_active_window(client, db, pos_auth_headers, test_brand, test_site):
    """GET /pos/menu-layout includes a published layout whose active-time window covers now (all 7 days, wide hours)."""
    from app.models.menu_layout import MenuLayout

    layout = MenuLayout(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        site_id=None,
        scope="brand",
        name="All Day Window Menu",
        is_published=True,
        version=2,
        is_all_day=False,
        start_time=time(0, 0),
        end_time=time(23, 59),
        active_days=[0, 1, 2, 3, 4, 5, 6],
    )
    db.add(layout)
    await db.commit()

    response = await client.get(f"/pos/menu-layout?site_id={test_site.id}", headers=pos_auth_headers)
    assert response.status_code == 200
    names = [l["name"] for l in response.json()]
    assert "All Day Window Menu" in names
