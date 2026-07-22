"""Integration tests for table maps & floor service routes (Android POS Phase 4).

Covers:
1. Happy path — create/list/detail a map, add shapes, publish/unpublish, duplicate
2. Auth failure — no token returns 401/403; POS terminal token blocked from authoring
3. Invalid input — missing fields return 422
4. Business rules — foreign brand site rejected, double-seat rejected, merge/clear rules
5. Audit log — TABLE_MAP_CREATED, TABLE_MAP_SHAPE_ADDED, TABLE_MAP_PUBLISHED,
   TABLE_SESSION_SEATED/ORDERED/BILLED/MERGED/CLEARED
6. Idempotency — repeated seat/clear calls with the same client_ref/on an
   already-closed session don't double-write
"""

import uuid

import pytest
from sqlalchemy import select

from app.constants.audit_actions import (
    TABLE_MAP_CREATED,
    TABLE_MAP_PUBLISHED,
    TABLE_MAP_SHAPE_ADDED,
    TABLE_SESSION_BILLED,
    TABLE_SESSION_CLEARED,
    TABLE_SESSION_MERGED,
    TABLE_SESSION_ORDERED,
    TABLE_SESSION_SEATED,
)
from app.models.audit_log import AuditLog
from app.models.dining_table import DiningTable
from app.models.table_session import TableSession

pytestmark = pytest.mark.asyncio


async def _create_map(client, headers, site_id, name="Ground Floor"):
    """Create a table map via the API and return its id."""
    resp = await client.post("/table-maps", json={"name": name, "site_id": str(site_id)}, headers=headers)
    return resp.json()["id"]


async def _create_table_shape(client, headers, table_map_id, label="T1", x=10.0, y=10.0):
    """Add a seatable 'round' shape to a map and return the response body."""
    resp = await client.post(
        f"/table-maps/{table_map_id}/shapes",
        json={"kind": "round", "label": label, "x": x, "y": y, "w": 10, "h": 10},
        headers=headers,
    )
    return resp.json()


# ── Map CRUD — happy path ───────────────────────────────────────────────────


async def test_create_table_map_returns_201(client, mgmt_auth_headers, test_site):
    """POST /table-maps creates a map for a site."""
    response = await client.post(
        "/table-maps", json={"name": "Ground Floor", "site_id": str(test_site.id)}, headers=mgmt_auth_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Ground Floor"
    assert body["site_id"] == str(test_site.id)
    assert body["is_published"] is False
    assert body["is_active"] is True


async def test_create_table_map_writes_audit_log(client, db, mgmt_auth_headers, test_site, test_user):
    """Creating a map writes a TABLE_MAP_CREATED audit row."""
    await _create_map(client, mgmt_auth_headers, test_site.id)

    result = await db.execute(select(AuditLog).where(AuditLog.action == TABLE_MAP_CREATED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_list_table_maps_includes_created(client, mgmt_auth_headers, test_site):
    """GET /table-maps lists maps for the brand."""
    await _create_map(client, mgmt_auth_headers, test_site.id, name="Rooftop")

    response = await client.get("/table-maps", headers=mgmt_auth_headers)
    assert response.status_code == 200
    names = [m["name"] for m in response.json()]
    assert "Rooftop" in names


async def test_get_table_map_detail_includes_empty_shapes(client, mgmt_auth_headers, test_site):
    """GET /table-maps/{id} returns shapes=[] for a fresh map."""
    map_id = await _create_map(client, mgmt_auth_headers, test_site.id)

    response = await client.get(f"/table-maps/{map_id}", headers=mgmt_auth_headers)
    assert response.status_code == 200
    assert response.json()["shapes"] == []


async def test_rename_table_map(client, mgmt_auth_headers, test_site):
    """PATCH /table-maps/{id} renames a map."""
    map_id = await _create_map(client, mgmt_auth_headers, test_site.id, name="Old Name")

    response = await client.patch(f"/table-maps/{map_id}", json={"name": "New Name"}, headers=mgmt_auth_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


async def test_delete_table_map_is_soft_delete(client, mgmt_auth_headers, test_site, db):
    """DELETE /table-maps/{id} soft-deletes — excluded from list, but the row remains."""
    map_id = await _create_map(client, mgmt_auth_headers, test_site.id)

    response = await client.delete(f"/table-maps/{map_id}", headers=mgmt_auth_headers)
    assert response.status_code == 204

    list_resp = await client.get("/table-maps", headers=mgmt_auth_headers)
    assert map_id not in [m["id"] for m in list_resp.json()]

    detail_resp = await client.get(f"/table-maps/{map_id}", headers=mgmt_auth_headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["is_active"] is False


async def test_duplicate_table_map(client, mgmt_auth_headers, test_site):
    """POST /table-maps/{id}/duplicate copies the map and its shapes."""
    map_id = await _create_map(client, mgmt_auth_headers, test_site.id, name="Original")
    await _create_table_shape(client, mgmt_auth_headers, map_id)

    response = await client.post(f"/table-maps/{map_id}/duplicate", headers=mgmt_auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Original (copy)"
    assert body["is_published"] is False

    detail = await client.get(f"/table-maps/{body['id']}", headers=mgmt_auth_headers)
    assert len(detail.json()["shapes"]) == 1


# ── Shape CRUD ────────────────────────────────────────────────────────────────


async def test_create_table_shape_creates_dining_table(client, db, mgmt_auth_headers, test_site):
    """A table-kind shape (round/stool/rect) also gets a 1:1 DiningTable row."""
    map_id = await _create_map(client, mgmt_auth_headers, test_site.id)

    body = await _create_table_shape(client, mgmt_auth_headers, map_id, label="T3")
    assert body["kind"] == "round"
    assert body["dining_table_id"] is not None

    result = await db.execute(select(DiningTable).where(DiningTable.id == uuid.UUID(body["dining_table_id"])))
    dining_table = result.scalar_one()
    assert dining_table.site_id == test_site.id


async def test_create_decor_shape_has_no_dining_table(client, mgmt_auth_headers, test_site):
    """A decorative shape (zone/bar_counter/entrance/wall) does not get a DiningTable row."""
    map_id = await _create_map(client, mgmt_auth_headers, test_site.id)

    response = await client.post(
        f"/table-maps/{map_id}/shapes",
        json={"kind": "zone", "label": "Patio", "x": 0, "y": 0, "w": 50, "h": 50, "dashed": True},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["dining_table_id"] is None
    assert body["dashed"] is True


async def test_create_shape_writes_audit_log(client, db, mgmt_auth_headers, test_site, test_user):
    """Adding a shape writes a TABLE_MAP_SHAPE_ADDED audit row."""
    map_id = await _create_map(client, mgmt_auth_headers, test_site.id)
    await _create_table_shape(client, mgmt_auth_headers, map_id)

    result = await db.execute(select(AuditLog).where(AuditLog.action == TABLE_MAP_SHAPE_ADDED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_update_shape_repositions(client, mgmt_auth_headers, test_site):
    """PATCH .../shapes/{id} repositions a shape."""
    map_id = await _create_map(client, mgmt_auth_headers, test_site.id)
    shape = await _create_table_shape(client, mgmt_auth_headers, map_id)

    response = await client.patch(
        f"/table-maps/{map_id}/shapes/{shape['id']}", json={"x": 42.5, "is_locked": True}, headers=mgmt_auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["x"] == 42.5
    assert body["is_locked"] is True


async def test_delete_shape_cascades_dining_table(client, db, mgmt_auth_headers, test_site):
    """DELETE .../shapes/{id} removes the shape and its DiningTable."""
    map_id = await _create_map(client, mgmt_auth_headers, test_site.id)
    shape = await _create_table_shape(client, mgmt_auth_headers, map_id)
    dining_table_id = uuid.UUID(shape["dining_table_id"])

    response = await client.delete(f"/table-maps/{map_id}/shapes/{shape['id']}", headers=mgmt_auth_headers)
    assert response.status_code == 204

    result = await db.execute(select(DiningTable).where(DiningTable.id == dining_table_id))
    assert result.scalar_one_or_none() is None


# ── Publish / unpublish ──────────────────────────────────────────────────────


async def test_publish_table_map(client, mgmt_auth_headers, test_site):
    """POST /table-maps/{id}/publish marks the map published."""
    map_id = await _create_map(client, mgmt_auth_headers, test_site.id)

    response = await client.post(f"/table-maps/{map_id}/publish", headers=mgmt_auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["is_published"] is True
    assert body["published_at"] is not None


async def test_publish_writes_audit_log(client, db, mgmt_auth_headers, test_site, test_user):
    """Publishing writes a TABLE_MAP_PUBLISHED audit row."""
    map_id = await _create_map(client, mgmt_auth_headers, test_site.id)
    await client.post(f"/table-maps/{map_id}/publish", headers=mgmt_auth_headers)

    result = await db.execute(select(AuditLog).where(AuditLog.action == TABLE_MAP_PUBLISHED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_unpublish_table_map(client, mgmt_auth_headers, test_site):
    """POST /table-maps/{id}/unpublish reverts is_published to False."""
    map_id = await _create_map(client, mgmt_auth_headers, test_site.id)
    await client.post(f"/table-maps/{map_id}/publish", headers=mgmt_auth_headers)

    response = await client.post(f"/table-maps/{map_id}/unpublish", headers=mgmt_auth_headers)
    assert response.status_code == 200
    assert response.json()["is_published"] is False


# ── Auth ──────────────────────────────────────────────────────────────────────


async def test_list_table_maps_no_token_returns_403(client):
    """GET /table-maps with no Authorization header is rejected."""
    response = await client.get("/table-maps")
    assert response.status_code in (401, 403)


async def test_create_table_map_pos_token_returns_403(client, pos_auth_headers, test_site):
    """POST /table-maps with a POS terminal token is blocked from authoring."""
    response = await client.post(
        "/table-maps", json={"name": "Blocked", "site_id": str(test_site.id)}, headers=pos_auth_headers
    )
    assert response.status_code == 403


# ── Invalid input / business rules ──────────────────────────────────────────


async def test_create_table_map_foreign_site_returns_400(client, mgmt_auth_headers):
    """POST /table-maps with a site_id from another brand is rejected."""
    response = await client.post(
        "/table-maps", json={"name": "Foreign", "site_id": str(uuid.uuid4())}, headers=mgmt_auth_headers
    )
    assert response.status_code == 400


async def test_create_table_map_missing_name_returns_422(client, mgmt_auth_headers, test_site):
    """POST /table-maps without a name is rejected."""
    response = await client.post("/table-maps", json={"site_id": str(test_site.id)}, headers=mgmt_auth_headers)
    assert response.status_code == 422


async def test_create_shape_invalid_kind_returns_422(client, mgmt_auth_headers, test_site):
    """POST .../shapes with an unrecognised kind is rejected."""
    map_id = await _create_map(client, mgmt_auth_headers, test_site.id)
    response = await client.post(
        f"/table-maps/{map_id}/shapes",
        json={"kind": "not_a_kind", "label": "X", "x": 0, "y": 0, "w": 10, "h": 10},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 422


# ── POS read contract ────────────────────────────────────────────────────────


async def test_pos_table_map_excludes_unpublished(client, mgmt_auth_headers, pos_auth_headers, test_site):
    """GET /pos/table-map excludes maps that have never been published."""
    await _create_map(client, mgmt_auth_headers, test_site.id, name="Unpublished")

    response = await client.get(f"/pos/table-map?site_id={test_site.id}", headers=pos_auth_headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_pos_table_map_returns_published_with_open_status(client, mgmt_auth_headers, pos_auth_headers, test_site):
    """GET /pos/table-map returns a published map; an unoccupied table has status=None."""
    map_id = await _create_map(client, mgmt_auth_headers, test_site.id)
    shape = await _create_table_shape(client, mgmt_auth_headers, map_id, label="T5")
    await client.post(f"/table-maps/{map_id}/publish", headers=mgmt_auth_headers)

    response = await client.get(f"/pos/table-map?site_id={test_site.id}", headers=pos_auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    shape_out = body[0]["shapes"][0]
    assert shape_out["label"] == "T5"
    assert shape_out["status"] is None
    assert shape_out["dining_table_id"] == shape["dining_table_id"]


async def test_pos_table_map_wrong_site_returns_403(client, pos_auth_headers):
    """GET /pos/table-map with a site_id other than the POS token's own site is rejected."""
    response = await client.get(f"/pos/table-map?site_id={uuid.uuid4()}", headers=pos_auth_headers)
    assert response.status_code == 403


# ── Live status mutations ────────────────────────────────────────────────────


async def _publish_map_with_table(client, headers, site_id, label="T9"):
    """Create, populate, and publish a map with one seatable shape; return the dining_table_id."""
    map_id = await _create_map(client, headers, site_id)
    shape = await _create_table_shape(client, headers, map_id, label=label)
    await client.post(f"/table-maps/{map_id}/publish", headers=headers)
    return shape["dining_table_id"]


async def test_seat_table_returns_201(client, mgmt_auth_headers, pos_auth_headers, test_site):
    """POST /pos/dining-tables/{id}/seat opens a session."""
    dining_table_id = await _publish_map_with_table(client, mgmt_auth_headers, test_site.id)

    response = await client.post(
        f"/pos/dining-tables/{dining_table_id}/seat", json={"covers": 4}, headers=pos_auth_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "seated"
    assert body["covers"] == 4
    assert body["closed_at"] is None


async def test_seat_table_writes_audit_log(client, db, mgmt_auth_headers, pos_auth_headers, test_site, test_user):
    """Seating a table writes a TABLE_SESSION_SEATED audit row."""
    dining_table_id = await _publish_map_with_table(client, mgmt_auth_headers, test_site.id)
    await client.post(f"/pos/dining-tables/{dining_table_id}/seat", json={"covers": 2}, headers=pos_auth_headers)

    result = await db.execute(select(AuditLog).where(AuditLog.action == TABLE_SESSION_SEATED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_seat_already_occupied_table_returns_409(client, mgmt_auth_headers, pos_auth_headers, test_site):
    """Seating an already-occupied table is rejected."""
    dining_table_id = await _publish_map_with_table(client, mgmt_auth_headers, test_site.id)
    await client.post(f"/pos/dining-tables/{dining_table_id}/seat", json={"covers": 2}, headers=pos_auth_headers)

    response = await client.post(
        f"/pos/dining-tables/{dining_table_id}/seat", json={"covers": 3}, headers=pos_auth_headers
    )
    assert response.status_code == 409


async def test_seat_table_idempotent_via_client_ref(client, db, mgmt_auth_headers, pos_auth_headers, test_site):
    """A retried seat call with the same client_ref returns the original session, not a duplicate."""
    dining_table_id = await _publish_map_with_table(client, mgmt_auth_headers, test_site.id)
    client_ref = str(uuid.uuid4())

    first = await client.post(
        f"/pos/dining-tables/{dining_table_id}/seat",
        json={"covers": 2, "client_ref": client_ref},
        headers=pos_auth_headers,
    )
    second = await client.post(
        f"/pos/dining-tables/{dining_table_id}/seat",
        json={"covers": 2, "client_ref": client_ref},
        headers=pos_auth_headers,
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    count_result = await db.execute(select(TableSession).where(TableSession.client_ref == client_ref))
    assert len(count_result.scalars().all()) == 1


async def test_order_then_bill_transitions(client, mgmt_auth_headers, pos_auth_headers, test_site, db):
    """order then bill move the session through its status sequence, each writing an audit row."""
    dining_table_id = await _publish_map_with_table(client, mgmt_auth_headers, test_site.id)
    seat_resp = await client.post(
        f"/pos/dining-tables/{dining_table_id}/seat", json={"covers": 2}, headers=pos_auth_headers
    )
    session_id = seat_resp.json()["id"]

    order_resp = await client.post(f"/pos/table-sessions/{session_id}/order", json={}, headers=pos_auth_headers)
    assert order_resp.status_code == 200
    assert order_resp.json()["status"] == "ordered"

    bill_resp = await client.post(f"/pos/table-sessions/{session_id}/bill", json={}, headers=pos_auth_headers)
    assert bill_resp.status_code == 200
    assert bill_resp.json()["status"] == "bill"

    ordered_log = await db.execute(select(AuditLog).where(AuditLog.action == TABLE_SESSION_ORDERED))
    ordered_log.scalar_one()
    bill_log = await db.execute(select(AuditLog).where(AuditLog.action == TABLE_SESSION_BILLED))
    bill_log.scalar_one()


async def test_clear_table_returns_to_open(client, mgmt_auth_headers, pos_auth_headers, test_site):
    """clear closes the session and the table reads as open again."""
    dining_table_id = await _publish_map_with_table(client, mgmt_auth_headers, test_site.id)
    seat_resp = await client.post(
        f"/pos/dining-tables/{dining_table_id}/seat", json={"covers": 2}, headers=pos_auth_headers
    )
    session_id = seat_resp.json()["id"]

    clear_resp = await client.post(f"/pos/table-sessions/{session_id}/clear", json={}, headers=pos_auth_headers)
    assert clear_resp.status_code == 200
    assert clear_resp.json()["closed_at"] is not None

    # Table can be seated again — proves DiningTable.active_session_id was cleared
    reseat_resp = await client.post(
        f"/pos/dining-tables/{dining_table_id}/seat", json={"covers": 5}, headers=pos_auth_headers
    )
    assert reseat_resp.status_code == 201
    assert reseat_resp.json()["id"] != session_id


async def test_clear_table_writes_audit_log(client, db, mgmt_auth_headers, pos_auth_headers, test_site, test_user):
    """Clearing a table writes a TABLE_SESSION_CLEARED audit row."""
    dining_table_id = await _publish_map_with_table(client, mgmt_auth_headers, test_site.id)
    seat_resp = await client.post(
        f"/pos/dining-tables/{dining_table_id}/seat", json={"covers": 2}, headers=pos_auth_headers
    )
    session_id = seat_resp.json()["id"]

    await client.post(f"/pos/table-sessions/{session_id}/clear", json={}, headers=pos_auth_headers)

    result = await db.execute(select(AuditLog).where(AuditLog.action == TABLE_SESSION_CLEARED))
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_clear_table_idempotent(client, mgmt_auth_headers, pos_auth_headers, test_site):
    """Clearing an already-cleared session is a no-op, not an error."""
    dining_table_id = await _publish_map_with_table(client, mgmt_auth_headers, test_site.id)
    seat_resp = await client.post(
        f"/pos/dining-tables/{dining_table_id}/seat", json={"covers": 2}, headers=pos_auth_headers
    )
    session_id = seat_resp.json()["id"]

    first = await client.post(f"/pos/table-sessions/{session_id}/clear", json={}, headers=pos_auth_headers)
    second = await client.post(f"/pos/table-sessions/{session_id}/clear", json={}, headers=pos_auth_headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["closed_at"] == second.json()["closed_at"]


async def test_merge_two_table_sessions(client, mgmt_auth_headers, pos_auth_headers, test_site, db):
    """merge bidirectionally links two open sessions."""
    dt1 = await _publish_map_with_table(client, mgmt_auth_headers, test_site.id, label="T1")
    map2_id = await _create_map(client, mgmt_auth_headers, test_site.id, name="Second Map")
    shape2 = await _create_table_shape(client, mgmt_auth_headers, map2_id, label="T2")
    await client.post(f"/table-maps/{map2_id}/publish", headers=mgmt_auth_headers)
    dt2 = shape2["dining_table_id"]

    seat1 = await client.post(f"/pos/dining-tables/{dt1}/seat", json={"covers": 2}, headers=pos_auth_headers)
    seat2 = await client.post(f"/pos/dining-tables/{dt2}/seat", json={"covers": 2}, headers=pos_auth_headers)
    session1_id = seat1.json()["id"]
    session2_id = seat2.json()["id"]

    response = await client.post(
        f"/pos/table-sessions/{session1_id}/merge", json={"partner_session_id": session2_id}, headers=pos_auth_headers
    )
    assert response.status_code == 200
    assert response.json()["merge_partner_session_id"] == session2_id

    partner_result = await db.execute(select(TableSession).where(TableSession.id == uuid.UUID(session2_id)))
    partner = partner_result.scalar_one()
    assert partner.merge_partner_session_id == uuid.UUID(session1_id)

    log_result = await db.execute(select(AuditLog).where(AuditLog.action == TABLE_SESSION_MERGED))
    log_result.scalar_one()


async def test_merge_already_merged_session_returns_400(client, mgmt_auth_headers, pos_auth_headers, test_site):
    """Merging a session that's already merged (or merging with itself) is rejected."""
    dt1 = await _publish_map_with_table(client, mgmt_auth_headers, test_site.id, label="T1")
    map2_id = await _create_map(client, mgmt_auth_headers, test_site.id, name="Second Map")
    shape2 = await _create_table_shape(client, mgmt_auth_headers, map2_id, label="T2")
    await client.post(f"/table-maps/{map2_id}/publish", headers=mgmt_auth_headers)
    map3_id = await _create_map(client, mgmt_auth_headers, test_site.id, name="Third Map")
    shape3 = await _create_table_shape(client, mgmt_auth_headers, map3_id, label="T3")
    await client.post(f"/table-maps/{map3_id}/publish", headers=mgmt_auth_headers)

    seat1 = await client.post(f"/pos/dining-tables/{dt1}/seat", json={"covers": 2}, headers=pos_auth_headers)
    seat2 = await client.post(
        f"/pos/dining-tables/{shape2['dining_table_id']}/seat", json={"covers": 2}, headers=pos_auth_headers
    )
    seat3 = await client.post(
        f"/pos/dining-tables/{shape3['dining_table_id']}/seat", json={"covers": 2}, headers=pos_auth_headers
    )
    session1_id = seat1.json()["id"]
    session2_id = seat2.json()["id"]
    session3_id = seat3.json()["id"]

    await client.post(
        f"/pos/table-sessions/{session1_id}/merge", json={"partner_session_id": session2_id}, headers=pos_auth_headers
    )
    # session1 already merged with session2 — merging with session3 should fail
    response = await client.post(
        f"/pos/table-sessions/{session1_id}/merge", json={"partner_session_id": session3_id}, headers=pos_auth_headers
    )
    assert response.status_code == 400
