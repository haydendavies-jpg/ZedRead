"""Integration tests for /brands routes.

Covers all five required scenarios per tests_CLAUDE.md:
1. Happy path — correct response shape, Uncategorised auto-created
2. Auth failure — no token → 403
3. Invalid input — missing fields → 422
4. Business rule — 404 for unknown brand/group, 409 for duplicate state change
5. Audit log — every write asserts the correct audit_logs row
"""

import uuid

from sqlalchemy import select

from app.constants.audit_actions import BRAND_ACTIVATED, BRAND_CREATED, BRAND_SUSPENDED, BRAND_UPDATED
from app.constants.statuses import GrantScope, SystemAccessProfile
from app.models.access_profile import AccessProfile
from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.user import User
from app.models.user_access_grant import UserAccessGrant


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_create_brand_returns_201(client, portal_auth_headers, test_group):
    """POST /brands creates a brand and returns 201 with the correct shape."""
    response = await client.post(
        "/brands/",
        json={"group_id": str(test_group.id), "name": "Burger Chain"},
        headers=portal_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Burger Chain"
    assert body["group_id"] == str(test_group.id)
    assert body["is_active"] is True


async def test_create_brand_auto_creates_uncategorised_category(client, db, portal_auth_headers, test_group):
    """Creating a brand automatically creates an 'Uncategorised' system category."""
    response = await client.post(
        "/brands/",
        json={"group_id": str(test_group.id), "name": "Pizza Place"},
        headers=portal_auth_headers,
    )
    brand_id = response.json()["id"]

    result = await db.execute(
        select(Category).where(
            Category.brand_id == uuid.UUID(brand_id),
            Category.is_system.is_(True),
        )
    )
    category = result.scalar_one()
    assert category.name == "Uncategorised"
    assert category.is_active is True


async def test_list_brands_returns_200(client, portal_auth_headers, test_brand):
    """GET /brands returns 200 with a list containing the seeded brand."""
    response = await client.get("/brands/", headers=portal_auth_headers)

    assert response.status_code == 200
    ids = [b["id"] for b in response.json()]
    assert str(test_brand.id) in ids


async def test_get_brand_returns_correct_brand(client, portal_auth_headers, test_brand):
    """GET /brands/{id} returns the correct brand."""
    response = await client.get(f"/brands/{test_brand.id}", headers=portal_auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(test_brand.id)


async def test_update_brand_name(client, portal_auth_headers, test_brand):
    """PATCH /brands/{id} updates the name."""
    response = await client.patch(
        f"/brands/{test_brand.id}", json={"name": "New Brand Name"}, headers=portal_auth_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "New Brand Name"


async def test_suspend_and_activate_brand(client, portal_auth_headers, test_brand):
    """POST /brands/{id}/suspend then /activate toggles is_active."""
    r1 = await client.post(f"/brands/{test_brand.id}/suspend", headers=portal_auth_headers)
    assert r1.status_code == 200
    assert r1.json()["is_active"] is False

    r2 = await client.post(f"/brands/{test_brand.id}/activate", headers=portal_auth_headers)
    assert r2.status_code == 200
    assert r2.json()["is_active"] is True


# ── Auth failure ──────────────────────────────────────────────────────────────


async def test_list_brands_no_token_returns_403(client):
    """GET /brands without a token returns 403."""
    response = await client.get("/brands/")
    assert response.status_code == 403


async def test_create_brand_no_token_returns_403(client, test_group):
    """POST /brands without a token returns 403."""
    response = await client.post(
        "/brands/", json={"group_id": str(test_group.id), "name": "Test"}
    )
    assert response.status_code == 403


# ── Invalid input ─────────────────────────────────────────────────────────────


async def test_create_brand_missing_name_returns_422(client, portal_auth_headers, test_group):
    """POST /brands with no name returns 422."""
    response = await client.post(
        "/brands/", json={"group_id": str(test_group.id)}, headers=portal_auth_headers
    )
    assert response.status_code == 422


async def test_create_brand_missing_group_id_returns_422(client, portal_auth_headers):
    """POST /brands with no group_id returns 422."""
    response = await client.post(
        "/brands/", json={"name": "No Group"}, headers=portal_auth_headers
    )
    assert response.status_code == 422


# ── Business rule violations ──────────────────────────────────────────────────


async def test_create_brand_unknown_group_returns_404(client, portal_auth_headers):
    """POST /brands with a non-existent group_id returns 404."""
    response = await client.post(
        "/brands/",
        json={"group_id": str(uuid.uuid4()), "name": "Orphan Brand"},
        headers=portal_auth_headers,
    )
    assert response.status_code == 404


async def test_get_unknown_brand_returns_404(client, portal_auth_headers):
    """GET /brands/{unknown_id} returns 404."""
    response = await client.get(f"/brands/{uuid.uuid4()}", headers=portal_auth_headers)
    assert response.status_code == 404


async def test_suspend_already_suspended_brand_returns_409(client, portal_auth_headers, test_brand):
    """Suspending an already-suspended brand returns 409."""
    await client.post(f"/brands/{test_brand.id}/suspend", headers=portal_auth_headers)
    response = await client.post(f"/brands/{test_brand.id}/suspend", headers=portal_auth_headers)
    assert response.status_code == 409


# ── Audit log assertions ──────────────────────────────────────────────────────


async def test_create_brand_writes_audit_log(client, db, portal_auth_headers, test_group):
    """POST /brands writes a BRAND_CREATED audit row."""
    response = await client.post(
        "/brands/",
        json={"group_id": str(test_group.id), "name": "Audit Brand"},
        headers=portal_auth_headers,
    )
    brand_id = response.json()["id"]

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == brand_id,
            AuditLog.action == BRAND_CREATED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["name"] == "Audit Brand"


async def test_update_brand_writes_audit_log(client, db, portal_auth_headers, test_brand):
    """PATCH /brands/{id} writes a BRAND_UPDATED audit row with before/after."""
    await client.patch(
        f"/brands/{test_brand.id}", json={"name": "Updated"}, headers=portal_auth_headers
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_brand.id),
            AuditLog.action == BRAND_UPDATED,
        )
    )
    row = result.scalar_one()
    assert row.before_state["name"] == "Test Brand"
    assert row.after_state["name"] == "Updated"


async def test_suspend_brand_writes_audit_log(client, db, portal_auth_headers, test_brand):
    """POST /brands/{id}/suspend writes a BRAND_SUSPENDED audit row."""
    await client.post(f"/brands/{test_brand.id}/suspend", headers=portal_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_brand.id),
            AuditLog.action == BRAND_SUSPENDED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["is_active"] is False


# ── Master User auto-creation ───────────────────────────────────────────────────


async def test_create_brand_seeds_brand_master_profile(client, db, portal_auth_headers, test_group):
    """POST /brands seeds the brand's Master User AccessProfile (among the 5 system tiers)."""
    response = await client.post(
        "/brands/",
        json={"group_id": str(test_group.id), "name": "Profile Test Brand"},
        headers=portal_auth_headers,
    )
    brand_id = response.json()["id"]

    result = await db.execute(
        select(AccessProfile).where(
            AccessProfile.brand_id == uuid.UUID(brand_id),
            AccessProfile.name == SystemAccessProfile.MASTER.value,
        )
    )
    profile = result.scalar_one()
    assert profile.is_system is True
    assert profile.group_id is None


async def test_create_brand_auto_creates_master_user(client, db, portal_auth_headers, test_group):
    """POST /brands auto-creates an immutable Master User scoped to the brand."""
    response = await client.post(
        "/brands/",
        json={"group_id": str(test_group.id), "name": "Master User Test Brand"},
        headers=portal_auth_headers,
    )
    brand_id = response.json()["id"]

    result = await db.execute(
        select(User).where(
            User.brand_id == uuid.UUID(brand_id),
            User.is_master_user == True,  # noqa: E712
        )
    )
    master_user = result.scalar_one()
    assert master_user.group_id == test_group.id
    assert master_user.name == "Master User Test Brand"
    assert master_user.is_active is True

    grant_result = await db.execute(
        select(UserAccessGrant).where(UserAccessGrant.user_id == master_user.id)
    )
    grant = grant_result.scalar_one()
    assert grant.scope == GrantScope.BRAND
    assert grant.brand_id == uuid.UUID(brand_id)
    assert grant.backend_role == "admin"
    assert grant.is_default is True


async def test_create_brand_master_user_writes_audit_logs(client, db, portal_auth_headers, test_group):
    """POST /brands writes USER_CREATED and ACCESS_GRANT_CREATED audit rows for the Master User."""
    from app.constants.audit_actions import ACCESS_GRANT_CREATED, USER_CREATED

    response = await client.post(
        "/brands/",
        json={"group_id": str(test_group.id), "name": "Audit Master Brand"},
        headers=portal_auth_headers,
    )
    brand_id = response.json()["id"]

    user_result = await db.execute(
        select(User).where(
            User.brand_id == uuid.UUID(brand_id),
            User.is_master_user == True,  # noqa: E712
        )
    )
    master_user = user_result.scalar_one()

    user_audit = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(master_user.id),
            AuditLog.action == USER_CREATED,
        )
    )
    assert user_audit.scalar_one() is not None

    grant_audit = await db.execute(
        select(AuditLog).where(
            AuditLog.action == ACCESS_GRANT_CREATED,
            AuditLog.after_state["user_id"].astext == str(master_user.id),
        )
    )
    assert grant_audit.scalar_one_or_none() is not None
