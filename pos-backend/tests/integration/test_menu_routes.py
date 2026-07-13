"""Integration tests for Menus routes (Menu Studio redesign).

Covers:
1. Happy path — create/list/update/duplicate a menu, schedule/cancel/publish
2. Auth failure — no token returns 403; POS terminal token returns 403 on writes
3. Invalid input — missing site_id for scope='site' returns 400
4. Business rules — foreign brand site rejected, scheduling a published menu rejected,
   scheduling a past timestamp rejected, cancelling a non-scheduled menu rejected
5. Audit log — MENU_CREATED, MENU_SCHEDULED, MENU_PUBLISHED written
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.constants.audit_actions import MENU_CREATED, MENU_PUBLISHED, MENU_SCHEDULED
from app.models.audit_log import AuditLog

pytestmark = pytest.mark.asyncio


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_create_brand_scope_menu_returns_201(client, mgmt_auth_headers, test_brand):
    """POST /menus creates a brand-wide draft menu."""
    response = await client.post(
        "/menus",
        json={"name": "Cafe — All Day", "note": "Primary in-store menu", "scope": "brand"},
        headers=mgmt_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Cafe — All Day"
    assert body["scope"] == "brand"
    assert body["site_id"] is None
    assert body["status"] == "draft"
    assert body["ref"].startswith("MNU-")


async def test_create_site_scope_menu_returns_201(client, mgmt_auth_headers, test_site):
    """POST /menus creates a site-specific draft menu."""
    response = await client.post(
        "/menus",
        json={"name": "Breakfast", "scope": "site", "site_id": str(test_site.id)},
        headers=mgmt_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["scope"] == "site"
    assert body["site_id"] == str(test_site.id)


async def test_create_menu_writes_audit_log(client, db, mgmt_auth_headers, test_user):
    """Creating a menu writes a MENU_CREATED audit row."""
    await client.post("/menus", json={"name": "Lunch", "scope": "brand"}, headers=mgmt_auth_headers)

    result = await db.execute(select(AuditLog).where(AuditLog.action == MENU_CREATED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_list_menus_returns_created_menu(client, mgmt_auth_headers, test_brand):
    """GET /menus returns menus for the brand."""
    await client.post("/menus", json={"name": "Happy Hour", "scope": "brand"}, headers=mgmt_auth_headers)

    response = await client.get("/menus", headers=mgmt_auth_headers)
    assert response.status_code == 200
    names = [m["name"] for m in response.json()]
    assert "Happy Hour" in names


async def test_update_menu_name(client, mgmt_auth_headers):
    """PATCH /menus/{id} updates the menu's name."""
    create_resp = await client.post("/menus", json={"name": "Draft Menu", "scope": "brand"}, headers=mgmt_auth_headers)
    menu_id = create_resp.json()["id"]

    patch_resp = await client.patch(f"/menus/{menu_id}", json={"name": "Renamed Menu"}, headers=mgmt_auth_headers)
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Renamed Menu"


async def test_duplicate_menu_creates_draft_copy(client, mgmt_auth_headers):
    """POST /menus/{id}/duplicate creates a new draft menu with a "(copy)" suffix."""
    create_resp = await client.post("/menus", json={"name": "Weekend Brunch", "scope": "brand"}, headers=mgmt_auth_headers)
    menu_id = create_resp.json()["id"]

    dup_resp = await client.post(f"/menus/{menu_id}/duplicate", headers=mgmt_auth_headers)
    assert dup_resp.status_code == 201
    body = dup_resp.json()
    assert body["name"] == "Weekend Brunch (copy)"
    assert body["status"] == "draft"
    assert body["id"] != menu_id


async def test_schedule_then_publish_menu(client, db, mgmt_auth_headers, test_user):
    """POST /menus/{id}/schedule sets status='scheduled'; publish then sets status='published'."""
    create_resp = await client.post("/menus", json={"name": "Scheduled Menu", "scope": "brand"}, headers=mgmt_auth_headers)
    menu_id = create_resp.json()["id"]

    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    sched_resp = await client.post(f"/menus/{menu_id}/schedule", json={"scheduled_at": future}, headers=mgmt_auth_headers)
    assert sched_resp.status_code == 200
    assert sched_resp.json()["status"] == "scheduled"

    result = await db.execute(select(AuditLog).where(AuditLog.action == MENU_SCHEDULED))
    assert result.scalar_one().actor_id == test_user.id

    publish_resp = await client.post(f"/menus/{menu_id}/publish", headers=mgmt_auth_headers)
    assert publish_resp.status_code == 200
    body = publish_resp.json()
    assert body["status"] == "published"
    assert body["published_at"] is not None

    result = await db.execute(select(AuditLog).where(AuditLog.action == MENU_PUBLISHED))
    assert result.scalar_one().actor_id == test_user.id


async def test_cancel_menu_schedule_reverts_to_draft(client, mgmt_auth_headers):
    """POST /menus/{id}/cancel-schedule reverts a scheduled menu to 'draft'."""
    create_resp = await client.post("/menus", json={"name": "Cancel Me", "scope": "brand"}, headers=mgmt_auth_headers)
    menu_id = create_resp.json()["id"]
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    await client.post(f"/menus/{menu_id}/schedule", json={"scheduled_at": future}, headers=mgmt_auth_headers)

    cancel_resp = await client.post(f"/menus/{menu_id}/cancel-schedule", headers=mgmt_auth_headers)
    assert cancel_resp.status_code == 200
    body = cancel_resp.json()
    assert body["status"] == "draft"
    assert body["scheduled_at"] is None


# ── Auth failure ─────────────────────────────────────────────────────────────


async def test_list_menus_no_token_returns_403(client):
    """GET /menus with no Authorization header returns 403 (HTTPBearer default)."""
    response = await client.get("/menus")
    assert response.status_code == 403


async def test_create_menu_pos_token_returns_403(client, pos_auth_headers):
    """POST /menus with a POS terminal token returns 403 — Menus is a management concept."""
    response = await client.post("/menus", json={"name": "Blocked", "scope": "brand"}, headers=pos_auth_headers)
    assert response.status_code == 403


# ── Invalid input / business rules ──────────────────────────────────────────


async def test_create_site_scope_menu_without_site_id_returns_400(client, mgmt_auth_headers):
    """POST /menus with scope='site' but no site_id returns 400."""
    response = await client.post("/menus", json={"name": "Bad Menu", "scope": "site"}, headers=mgmt_auth_headers)
    assert response.status_code == 400


async def test_create_menu_with_foreign_brand_site_returns_400(client, mgmt_auth_headers, db, test_brand, test_group):
    """POST /menus with a site_id belonging to another brand returns 400."""
    import uuid as uuid_mod

    from app.models.brand import Brand
    from app.models.site import Site

    other_brand = Brand(
        id=uuid_mod.uuid4(),
        group_id=test_group.id,
        name="Other Brand",
        is_active=True,
        timezone="Australia/Sydney",
        currency="AUD",
        country="AU",
    )
    db.add(other_brand)
    await db.flush()
    other_site = Site(
        id=uuid_mod.uuid4(),
        brand_id=other_brand.id,
        name="Other Site",
        is_active=True,
        timezone="Australia/Sydney",
        currency="AUD",
        country="AU",
        address_street="1 Other Street",
        address_state="NSW",
        address_postcode="2000",
    )
    db.add(other_site)
    await db.commit()

    response = await client.post(
        "/menus",
        json={"name": "Cross Brand", "scope": "site", "site_id": str(other_site.id)},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 400


async def test_schedule_published_menu_returns_400(client, mgmt_auth_headers):
    """POST /menus/{id}/schedule on an already-published menu returns 400."""
    create_resp = await client.post("/menus", json={"name": "Live Menu", "scope": "brand"}, headers=mgmt_auth_headers)
    menu_id = create_resp.json()["id"]
    await client.post(f"/menus/{menu_id}/publish", headers=mgmt_auth_headers)

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    response = await client.post(f"/menus/{menu_id}/schedule", json={"scheduled_at": future}, headers=mgmt_auth_headers)
    assert response.status_code == 400


async def test_schedule_menu_in_the_past_returns_400(client, mgmt_auth_headers):
    """POST /menus/{id}/schedule with a past timestamp returns 400."""
    create_resp = await client.post("/menus", json={"name": "Past Menu", "scope": "brand"}, headers=mgmt_auth_headers)
    menu_id = create_resp.json()["id"]

    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    response = await client.post(f"/menus/{menu_id}/schedule", json={"scheduled_at": past}, headers=mgmt_auth_headers)
    assert response.status_code == 400


async def test_cancel_schedule_on_draft_menu_returns_400(client, mgmt_auth_headers):
    """POST /menus/{id}/cancel-schedule on a non-scheduled menu returns 400."""
    create_resp = await client.post("/menus", json={"name": "Never Scheduled", "scope": "brand"}, headers=mgmt_auth_headers)
    menu_id = create_resp.json()["id"]

    response = await client.post(f"/menus/{menu_id}/cancel-schedule", headers=mgmt_auth_headers)
    assert response.status_code == 400
