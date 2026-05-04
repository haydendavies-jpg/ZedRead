"""Integration tests for /portal-users routes.

Covers all five required scenarios per tests_CLAUDE.md:
1. Happy path — correct response shape, correct status codes
2. Auth failure — non-super_admin gets 403 (all routes require super_admin role)
3. Invalid input — missing fields → 422, short password → 422
4. Business rule — 409 duplicate email, 400 self-suspend, 404 unknown user
5. Audit log — every write asserts the correct audit_logs row
"""

import uuid

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import PORTAL_USER_ACTIVATED, PORTAL_USER_CREATED, PORTAL_USER_SUSPENDED
from app.models.audit_log import AuditLog
from app.models.portal_user import PortalUser
from app.utils.security import create_access_token, hash_password


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def second_portal_user(db: AsyncSession) -> PortalUser:
    """A second persisted PortalUser that super_admin can act upon."""
    user = PortalUser(
        id=uuid.uuid4(),
        email="target@test.com",
        password_hash=hash_password("AnotherPassword123!"),
        name="Target User",
        role="admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture()
async def admin_auth_headers(db: AsyncSession) -> dict[str, str]:
    """Auth headers for a regular admin (not super_admin) — should be denied on all portal-user routes."""
    user = PortalUser(
        id=uuid.uuid4(),
        email="regular_admin@test.com",
        password_hash=hash_password("RegularPassword123!"),
        name="Regular Admin",
        role="admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token(str(user.id), user.role)
    return {"Authorization": f"Bearer {token}"}


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_create_portal_user_returns_201(client, portal_auth_headers):
    """POST /portal-users creates a portal user and returns 201 with correct shape."""
    response = await client.post(
        "/portal-users/",
        json={
            "email": "new_user@test.com",
            "name": "New User",
            "password": "SecurePassword123!",
            "role": "admin",
        },
        headers=portal_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new_user@test.com"
    assert body["name"] == "New User"
    assert body["role"] == "admin"
    assert body["is_active"] is True
    assert "password_hash" not in body
    assert "password" not in body


async def test_list_portal_users_returns_200(client, portal_auth_headers, test_portal_user):
    """GET /portal-users returns 200 with a list containing the seeded user."""
    response = await client.get("/portal-users/", headers=portal_auth_headers)

    assert response.status_code == 200
    ids = [u["id"] for u in response.json()]
    assert str(test_portal_user.id) in ids


async def test_get_portal_user_returns_correct_user(client, portal_auth_headers, test_portal_user):
    """GET /portal-users/{id} returns the correct portal user."""
    response = await client.get(f"/portal-users/{test_portal_user.id}", headers=portal_auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(test_portal_user.id)


async def test_update_portal_user_name(client, portal_auth_headers, second_portal_user):
    """PATCH /portal-users/{id} updates the user's name."""
    response = await client.patch(
        f"/portal-users/{second_portal_user.id}",
        json={"name": "Updated Name"},
        headers=portal_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"


async def test_suspend_and_activate_portal_user(client, portal_auth_headers, second_portal_user):
    """POST /portal-users/{id}/suspend then /activate toggles is_active correctly."""
    r1 = await client.post(f"/portal-users/{second_portal_user.id}/suspend", headers=portal_auth_headers)
    assert r1.status_code == 200
    assert r1.json()["is_active"] is False

    r2 = await client.post(f"/portal-users/{second_portal_user.id}/activate", headers=portal_auth_headers)
    assert r2.status_code == 200
    assert r2.json()["is_active"] is True


# ── Auth failure ──────────────────────────────────────────────────────────────


async def test_list_portal_users_no_token_returns_403(client):
    """GET /portal-users without a token returns 403."""
    response = await client.get("/portal-users/")
    assert response.status_code == 403


async def test_list_portal_users_non_super_admin_returns_403(client, admin_auth_headers):
    """GET /portal-users with a non-super_admin token returns 403."""
    response = await client.get("/portal-users/", headers=admin_auth_headers)
    assert response.status_code == 403


async def test_create_portal_user_non_super_admin_returns_403(client, admin_auth_headers):
    """POST /portal-users with a non-super_admin token returns 403."""
    response = await client.post(
        "/portal-users/",
        json={"email": "x@x.com", "name": "X", "password": "SecurePassword123!", "role": "admin"},
        headers=admin_auth_headers,
    )
    assert response.status_code == 403


# ── Invalid input ─────────────────────────────────────────────────────────────


async def test_create_portal_user_missing_email_returns_422(client, portal_auth_headers):
    """POST /portal-users with no email returns 422."""
    response = await client.post(
        "/portal-users/",
        json={"name": "No Email", "password": "SecurePassword123!", "role": "admin"},
        headers=portal_auth_headers,
    )
    assert response.status_code == 422


async def test_create_portal_user_short_password_returns_422(client, portal_auth_headers):
    """POST /portal-users with a password shorter than 12 chars returns 422."""
    response = await client.post(
        "/portal-users/",
        json={"email": "short@test.com", "name": "Short", "password": "tooshort", "role": "admin"},
        headers=portal_auth_headers,
    )
    assert response.status_code == 422


async def test_create_portal_user_invalid_role_returns_422(client, portal_auth_headers):
    """POST /portal-users with an unrecognised role returns 422."""
    response = await client.post(
        "/portal-users/",
        json={
            "email": "badrole@test.com",
            "name": "Bad Role",
            "password": "SecurePassword123!",
            "role": "god_mode",
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 422


# ── Business rule violations ──────────────────────────────────────────────────


async def test_create_portal_user_duplicate_email_returns_409(
    client, portal_auth_headers, test_portal_user
):
    """POST /portal-users with an already-registered email returns 409."""
    response = await client.post(
        "/portal-users/",
        json={
            "email": test_portal_user.email,
            "name": "Duplicate",
            "password": "SecurePassword123!",
            "role": "admin",
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 409


async def test_get_unknown_portal_user_returns_404(client, portal_auth_headers):
    """GET /portal-users/{unknown_id} returns 404."""
    response = await client.get(f"/portal-users/{uuid.uuid4()}", headers=portal_auth_headers)
    assert response.status_code == 404


async def test_suspend_self_returns_400(client, portal_auth_headers, test_portal_user):
    """POST /portal-users/{own_id}/suspend returns 400 — cannot suspend yourself."""
    response = await client.post(
        f"/portal-users/{test_portal_user.id}/suspend", headers=portal_auth_headers
    )
    assert response.status_code == 400


async def test_suspend_already_suspended_user_returns_409(
    client, portal_auth_headers, second_portal_user
):
    """Suspending an already-suspended user returns 409."""
    await client.post(f"/portal-users/{second_portal_user.id}/suspend", headers=portal_auth_headers)
    response = await client.post(
        f"/portal-users/{second_portal_user.id}/suspend", headers=portal_auth_headers
    )
    assert response.status_code == 409


async def test_activate_already_active_user_returns_409(
    client, portal_auth_headers, second_portal_user
):
    """Activating an already-active user returns 409."""
    response = await client.post(
        f"/portal-users/{second_portal_user.id}/activate", headers=portal_auth_headers
    )
    assert response.status_code == 409


# ── Audit log assertions ──────────────────────────────────────────────────────


async def test_create_portal_user_writes_audit_log(client, db, portal_auth_headers):
    """POST /portal-users writes a PORTAL_USER_CREATED audit row."""
    response = await client.post(
        "/portal-users/",
        json={
            "email": "audit@test.com",
            "name": "Audit User",
            "password": "SecurePassword123!",
            "role": "admin",
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 201
    user_id = response.json()["id"]

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == user_id,
            AuditLog.action == PORTAL_USER_CREATED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["email"] == "audit@test.com"


async def test_suspend_portal_user_writes_audit_log(
    client, db, portal_auth_headers, second_portal_user
):
    """POST /portal-users/{id}/suspend writes a PORTAL_USER_SUSPENDED audit row."""
    await client.post(f"/portal-users/{second_portal_user.id}/suspend", headers=portal_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(second_portal_user.id),
            AuditLog.action == PORTAL_USER_SUSPENDED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["is_active"] is False


async def test_activate_portal_user_writes_audit_log(
    client, db, portal_auth_headers, second_portal_user
):
    """POST /portal-users/{id}/activate writes a PORTAL_USER_ACTIVATED audit row."""
    await client.post(f"/portal-users/{second_portal_user.id}/suspend", headers=portal_auth_headers)
    await client.post(f"/portal-users/{second_portal_user.id}/activate", headers=portal_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(second_portal_user.id),
            AuditLog.action == PORTAL_USER_ACTIVATED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["is_active"] is True
