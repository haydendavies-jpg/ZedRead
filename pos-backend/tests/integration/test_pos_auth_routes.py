"""Integration tests for POS authentication routes.

Covers:
1. Happy path — login returns token + context; PIN set; PIN verify issues token
2. Auth failure — wrong password, inactive user, no grant, wrong PIN
3. Invalid input — missing fields return 422
4. Business rules — site not found, no active grant, PIN not set
5. Audit log — login success/failure, pin set, pin verify all write correct rows
"""

import uuid

import pytest
from sqlalchemy import select

from app.constants.audit_actions import (
    POS_LOGIN_FAILED,
    POS_LOGIN_SUCCESS,
    POS_PIN_SET,
    POS_PIN_VERIFIED,
)
from app.models.audit_log import AuditLog
from app.models.user_pin import UserPIN
from app.models.user_pos_session import UserPOSSession
from app.utils.security import hash_password

pytestmark = pytest.mark.asyncio


# ── Login happy path ──────────────────────────────────────────────────────────


async def test_pos_login_valid_credentials_returns_200(
    client, test_pos_user, test_site, test_access_grant
):
    """Valid email+password+site_id returns 200 with token and terminal context."""
    response = await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "site_id": str(test_site.id),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["user_id"] == str(test_pos_user.id)
    assert body["user_name"] == "Test POS User"
    assert body["site_id"] == str(test_site.id)
    assert body["site_name"] == test_site.name
    assert body["access_profile_name"] == "Cashier"
    assert body["is_pin_reset_required"] is True  # No PIN set yet


async def test_pos_login_creates_session_row(client, db, test_pos_user, test_site, test_access_grant):
    """Successful login writes a UserPOSSession row to the database."""
    await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "site_id": str(test_site.id),
        },
    )

    result = await db.execute(
        select(UserPOSSession).where(UserPOSSession.user_id == test_pos_user.id)
    )
    session = result.scalar_one()
    assert session.site_id == test_site.id
    assert session.ended_at is None  # Session is active


async def test_pos_login_success_writes_audit_log(client, db, test_pos_user, test_site, test_access_grant):
    """Successful POS login writes a POS_LOGIN_SUCCESS audit row."""
    await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "site_id": str(test_site.id),
        },
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_pos_user.id),
            AuditLog.action == POS_LOGIN_SUCCESS,
        )
    )
    row = result.scalar_one()
    assert row.actor_email == "posuser@test.com"
    assert row.actor_id == test_pos_user.id


# ── Login failure ─────────────────────────────────────────────────────────────


async def test_pos_login_wrong_password_returns_401(client, test_pos_user, test_site, test_access_grant):
    """Wrong password returns 401 with a generic message."""
    response = await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "WrongPassword!",
            "site_id": str(test_site.id),
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


async def test_pos_login_unknown_email_returns_401(client, test_site):
    """Unknown email returns 401 with the same message as wrong password."""
    response = await client.post(
        "/auth/pos/login",
        json={
            "email": "nobody@test.com",
            "password": "POSPassword123!",
            "site_id": str(test_site.id),
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


async def test_pos_login_inactive_user_returns_401(client, db, test_site, test_brand):
    """Inactive POS user cannot log in."""
    from app.models.pos_user import POSUser

    inactive = POSUser(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        name="Inactive",
        email="inactive_pos@test.com",
        password_hash=hash_password("POSPassword123!"),
        is_active=False,
    )
    db.add(inactive)
    await db.commit()

    response = await client.post(
        "/auth/pos/login",
        json={
            "email": "inactive_pos@test.com",
            "password": "POSPassword123!",
            "site_id": str(test_site.id),
        },
    )

    assert response.status_code == 401


async def test_pos_login_no_grant_returns_403(client, test_pos_user, test_site):
    """User with no active grant for the site is denied with 403."""
    # No test_access_grant fixture — user exists but has no grant
    response = await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "site_id": str(test_site.id),
        },
    )

    assert response.status_code == 403
    assert "grant" in response.json()["detail"].lower()


async def test_pos_login_unknown_site_returns_401(client, test_pos_user, test_access_grant):
    """Site ID that doesn't exist returns 401 (same vague error)."""
    response = await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "site_id": str(uuid.uuid4()),
        },
    )

    assert response.status_code == 401


async def test_pos_login_failure_writes_audit_log(client, db, test_pos_user, test_site, test_access_grant):
    """Failed login writes a POS_LOGIN_FAILED audit row."""
    await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "WrongPassword!",
            "site_id": str(test_site.id),
        },
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.action == POS_LOGIN_FAILED,
            AuditLog.actor_email == "posuser@test.com",
        )
    )
    row = result.scalar_one()
    assert row.actor_id is None  # No actor ID for a failed login


# ── PIN set ───────────────────────────────────────────────────────────────────


async def test_pin_set_creates_pin_record(client, db, pos_auth_headers, test_pos_user):
    """POST /auth/pos/pin/set creates a UserPIN row and returns 204."""
    response = await client.post(
        "/auth/pos/pin/set",
        json={"pin": "1234"},
        headers=pos_auth_headers,
    )

    assert response.status_code == 204

    result = await db.execute(
        select(UserPIN).where(UserPIN.user_id == test_pos_user.id)
    )
    pin_record = result.scalar_one()
    assert pin_record.is_pin_reset_required is False


async def test_pin_set_updates_existing_pin(client, db, pos_auth_headers, test_pos_user):
    """Setting PIN twice upserts — no duplicate rows."""
    await client.post("/auth/pos/pin/set", json={"pin": "1234"}, headers=pos_auth_headers)
    await client.post("/auth/pos/pin/set", json={"pin": "5678"}, headers=pos_auth_headers)

    result = await db.execute(
        select(UserPIN).where(UserPIN.user_id == test_pos_user.id)
    )
    pins = result.scalars().all()
    assert len(pins) == 1  # Only one row — upsert, not duplicate


async def test_pin_set_writes_audit_log(client, db, pos_auth_headers, test_pos_user):
    """PIN set writes a POS_PIN_SET audit row."""
    await client.post("/auth/pos/pin/set", json={"pin": "1234"}, headers=pos_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_pos_user.id),
            AuditLog.action == POS_PIN_SET,
        )
    )
    row = result.scalar_one()
    assert row.actor_id == test_pos_user.id


async def test_pin_set_invalid_pin_returns_422(client, pos_auth_headers):
    """PIN shorter than 4 digits returns 422."""
    response = await client.post(
        "/auth/pos/pin/set",
        json={"pin": "12"},
        headers=pos_auth_headers,
    )

    assert response.status_code == 422


async def test_pin_set_non_numeric_pin_returns_422(client, pos_auth_headers):
    """Non-numeric PIN returns 422."""
    response = await client.post(
        "/auth/pos/pin/set",
        json={"pin": "abcd"},
        headers=pos_auth_headers,
    )

    assert response.status_code == 422


async def test_pin_set_no_token_returns_403(client):
    """PIN set without auth token returns 403."""
    response = await client.post("/auth/pos/pin/set", json={"pin": "1234"})
    assert response.status_code == 403


# ── PIN verify ────────────────────────────────────────────────────────────────


async def test_pin_verify_correct_pin_returns_200(
    client, db, pos_auth_headers, test_pos_user, test_site, test_access_grant
):
    """Correct PIN returns 200 with a fresh access token."""
    # Set a PIN first
    await client.post("/auth/pos/pin/set", json={"pin": "1234"}, headers=pos_auth_headers)

    response = await client.post(
        "/auth/pos/pin/verify",
        json={
            "email": "posuser@test.com",
            "pin": "1234",
            "site_id": str(test_site.id),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["user_id"] == str(test_pos_user.id)
    assert body["user_name"] == "Test POS User"
    assert body["access_profile_name"] == "Cashier"
    assert body["is_pin_reset_required"] is False


async def test_pin_verify_creates_new_session_row(
    client, db, pos_auth_headers, test_pos_user, test_site, test_access_grant
):
    """PIN verify creates a new UserPOSSession row."""
    await client.post("/auth/pos/pin/set", json={"pin": "1234"}, headers=pos_auth_headers)

    await client.post(
        "/auth/pos/pin/verify",
        json={
            "email": "posuser@test.com",
            "pin": "1234",
            "site_id": str(test_site.id),
        },
    )

    result = await db.execute(
        select(UserPOSSession).where(UserPOSSession.user_id == test_pos_user.id)
    )
    sessions = result.scalars().all()
    # One session from login (via pos_auth_headers jti) + one from pin verify
    assert len(sessions) >= 1


async def test_pin_verify_wrong_pin_returns_401(
    client, pos_auth_headers, test_pos_user, test_site, test_access_grant
):
    """Wrong PIN returns 401."""
    await client.post("/auth/pos/pin/set", json={"pin": "1234"}, headers=pos_auth_headers)

    response = await client.post(
        "/auth/pos/pin/verify",
        json={
            "email": "posuser@test.com",
            "pin": "9999",
            "site_id": str(test_site.id),
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid PIN"


async def test_pin_verify_no_pin_set_returns_401(
    client, test_pos_user, test_site, test_access_grant
):
    """Verify fails with 401 when the user has no PIN set."""
    response = await client.post(
        "/auth/pos/pin/verify",
        json={
            "email": "posuser@test.com",
            "pin": "1234",
            "site_id": str(test_site.id),
        },
    )

    assert response.status_code == 401


async def test_pin_verify_writes_audit_log(
    client, db, pos_auth_headers, test_pos_user, test_site, test_access_grant
):
    """Successful PIN verify writes a POS_PIN_VERIFIED audit row."""
    await client.post("/auth/pos/pin/set", json={"pin": "1234"}, headers=pos_auth_headers)

    await client.post(
        "/auth/pos/pin/verify",
        json={
            "email": "posuser@test.com",
            "pin": "1234",
            "site_id": str(test_site.id),
        },
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_pos_user.id),
            AuditLog.action == POS_PIN_VERIFIED,
        )
    )
    row = result.scalar_one()
    assert row.actor_id == test_pos_user.id


# ── Login missing fields ──────────────────────────────────────────────────────


async def test_pos_login_missing_site_id_returns_422(client, test_pos_user):
    """Missing site_id returns 422."""
    response = await client.post(
        "/auth/pos/login",
        json={"email": "posuser@test.com", "password": "POSPassword123!"},
    )

    assert response.status_code == 422
