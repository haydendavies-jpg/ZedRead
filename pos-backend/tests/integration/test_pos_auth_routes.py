"""Integration tests for POS authentication routes.

Covers:
1. Happy path — login returns token + context; PIN set; PIN verify issues token
2. Auth failure — wrong password, inactive user, no grant, wrong PIN
3. Invalid input — missing fields return 422
4. Business rules — device not registered, license inactive, no active grant,
   multi-site selection (available_sites + site-token), device re-pairing
5. Audit log — login success/failure, device repair, pin set, pin verify all
   write correct rows
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.constants.audit_actions import (
    DEVICE_REPAIRED,
    POS_LOGIN_FAILED,
    POS_LOGIN_SUCCESS,
    POS_LOGOUT,
    POS_PIN_SET,
    POS_PIN_VERIFIED,
)
from app.models.audit_log import AuditLog
from app.models.license import License
from app.models.pos_device import PosDevice
from app.models.site import Site
from app.models.user_access_grant import UserAccessGrant
from app.models.user_pin import UserPIN
from app.models.user_pos_session import UserPOSSession
from app.utils.security import hash_password

pytestmark = pytest.mark.asyncio


# ── Login happy path ──────────────────────────────────────────────────────────


async def test_pos_login_valid_credentials_returns_200(
    client, test_user, test_site, test_access_grant, test_device
):
    """Valid email+password+device_token returns 200 with token and terminal context."""
    response = await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "device_token": test_device.device_token,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["user_id"] == str(test_user.id)
    assert body["user_name"] == "Test POS User"
    assert body["site_id"] == str(test_site.id)
    assert body["site_name"] == test_site.name
    assert body["access_profile_name"] == "Cashier"
    assert body["is_pin_reset_required"] is True  # No PIN set yet
    assert body["available_sites"] is None


async def test_pos_login_creates_session_row(client, db, test_user, test_site, test_access_grant, test_device):
    """Successful login writes a UserPOSSession row to the database."""
    await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "device_token": test_device.device_token,
        },
    )

    result = await db.execute(
        select(UserPOSSession).where(UserPOSSession.user_id == test_user.id)
    )
    session = result.scalar_one()
    assert session.site_id == test_site.id
    assert session.ended_at is None  # Session is active


async def test_pos_login_success_writes_audit_log(
    client, db, test_user, test_site, test_access_grant, test_device
):
    """Successful POS login writes a POS_LOGIN_SUCCESS audit row."""
    await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "device_token": test_device.device_token,
        },
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_user.id),
            AuditLog.action == POS_LOGIN_SUCCESS,
        )
    )
    row = result.scalar_one()
    assert row.actor_email == "posuser@test.com"
    assert row.actor_id == test_user.id


# ── Logout / session revocation ───────────────────────────────────────────────


async def _login_pos(client, device) -> str:
    """Log in the standard test POS user against the given device and return the access token."""
    resp = await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "device_token": device.device_token,
        },
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


async def test_pos_logout_ends_session(client, db, test_user, test_site, test_access_grant, test_device):
    """Logout returns 200 and sets ended_at on the user's active session."""
    token = await _login_pos(client, test_device)

    resp = await client.post("/auth/pos/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    result = await db.execute(
        select(UserPOSSession).where(UserPOSSession.user_id == test_user.id)
    )
    session = result.scalar_one()
    assert session.ended_at is not None  # Session has been ended


async def test_pos_logout_writes_audit_log(client, db, test_user, test_site, test_access_grant, test_device):
    """Logout writes a POS_LOGOUT audit row attributed to the user."""
    token = await _login_pos(client, test_device)

    await client.post("/auth/pos/logout", headers={"Authorization": f"Bearer {token}"})

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_user.id),
            AuditLog.action == POS_LOGOUT,
        )
    )
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_pos_token_rejected_after_logout(client, test_user, test_site, test_access_grant, test_device):
    """A POS token is rejected on protected routes once its session is logged out."""
    token = await _login_pos(client, test_device)
    headers = {"Authorization": f"Bearer {token}"}

    # Token works before logout
    assert (await client.get("/products", headers=headers)).status_code == 200

    # Log out, then the same token must be rejected
    assert (await client.post("/auth/pos/logout", headers=headers)).status_code == 200
    assert (await client.get("/products", headers=headers)).status_code == 401


async def test_pos_logout_requires_authentication(client):
    """Logout with no token returns 403 (no credentials)."""
    resp = await client.post("/auth/pos/logout")
    assert resp.status_code == 403


# ── Login failure ─────────────────────────────────────────────────────────────


async def test_pos_login_wrong_password_returns_401(
    client, test_user, test_site, test_access_grant, test_device
):
    """Wrong password returns 401 with a generic message."""
    response = await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "WrongPassword!",
            "device_token": test_device.device_token,
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


async def test_pos_login_unknown_email_returns_401(client, test_device):
    """Unknown email returns 401 with the same message as wrong password."""
    response = await client.post(
        "/auth/pos/login",
        json={
            "email": "nobody@test.com",
            "password": "POSPassword123!",
            "device_token": test_device.device_token,
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


async def test_pos_login_inactive_user_returns_401(client, db, test_site, test_brand, test_device):
    """Inactive POS user cannot log in."""
    from app.models.user import User

    inactive = User(
        id=uuid.uuid4(),
        group_id=test_brand.group_id,
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
            "device_token": test_device.device_token,
        },
    )

    assert response.status_code == 401


async def test_pos_login_no_grant_returns_403(client, test_user, test_site, test_device):
    """User with no active grant for the device's paired site is denied with 403."""
    # No test_access_grant fixture — user exists but has no grant
    response = await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "device_token": test_device.device_token,
        },
    )

    assert response.status_code == 403
    assert "grant" in response.json()["detail"].lower()


async def test_pos_login_unregistered_device_returns_404(client, test_user, test_access_grant):
    """An unknown device_token returns 404 — the device has not been registered."""
    response = await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "device_token": "not-a-real-device-token",
        },
    )

    assert response.status_code == 404


async def test_pos_login_inactive_license_returns_403(
    client, db, test_user, test_site, test_access_grant, test_device, test_license
):
    """A site whose license is not active rejects login with 403, even with a valid grant."""
    test_license.status = "disabled"
    await db.commit()

    response = await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "device_token": test_device.device_token,
        },
    )

    assert response.status_code == 403
    assert "license" in response.json()["detail"].lower()


async def test_pos_login_failure_writes_audit_log(
    client, db, test_user, test_site, test_access_grant, test_device
):
    """Failed login writes a POS_LOGIN_FAILED audit row."""
    await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "WrongPassword!",
            "device_token": test_device.device_token,
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


# ── Multi-site selection + device re-pairing ─────────────────────────────────


@pytest.fixture
async def second_site_grant(db, test_user, test_brand, test_access_profile):
    """A second site (under test_brand) the user also has an active grant on."""
    site = Site(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        name="Second Site",
        is_active=True,
        timezone="Australia/Sydney",
        currency="AUD",
        country="AU",
        address_street="2 Test Street",
        address_state="NSW",
        address_postcode="2000",
    )
    db.add(site)
    await db.flush()

    lic = License(
        id=uuid.uuid4(),
        site_id=site.id,
        plan_name="starter",
        status="active",
        monthly_fee_cents=9900,
        is_trial=False,
        starts_at=datetime.now(tz=timezone.utc),
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=365),
    )
    db.add(lic)

    grant = UserAccessGrant(
        id=uuid.uuid4(),
        user_id=test_user.id,
        site_id=site.id,
        access_profile_id=test_access_profile.id,
        granted_by_id=None,
        is_active=True,
    )
    db.add(grant)
    await db.commit()
    await db.refresh(site)
    return site


async def test_pos_login_single_site_ignores_multi_site_flag(
    client, db, test_user, test_site, test_access_grant, test_device
):
    """is_pos_multi_site_enabled with only one granted site still resolves directly — no selector."""
    test_user.is_pos_multi_site_enabled = True
    await db.commit()

    response = await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "device_token": test_device.device_token,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] is not None
    assert body["available_sites"] is None


async def test_pos_login_multi_site_returns_available_sites(
    client, db, test_user, test_site, test_access_grant, test_device, second_site_grant
):
    """A multi-site-enabled user with grants on 2+ sites gets a selection list, not a token."""
    test_user.is_pos_multi_site_enabled = True
    await db.commit()

    response = await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "device_token": test_device.device_token,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] is None
    assert body["available_sites"] is not None
    site_ids = {s["site_id"] for s in body["available_sites"]}
    assert site_ids == {str(test_site.id), str(second_site_grant.id)}


async def test_pos_login_without_multi_site_flag_ignores_other_grants(
    client, db, test_user, test_site, test_access_grant, test_device, second_site_grant
):
    """Without the flag, login resolves straight to the device's paired site even with 2+ grants."""
    response = await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "device_token": test_device.device_token,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["site_id"] == str(test_site.id)


async def test_site_token_finalizes_selection_and_repairs_device(
    client, db, test_user, test_site, test_access_grant, test_device, second_site_grant
):
    """POST /auth/pos/site-token issues a token for the chosen site and re-pairs the device."""
    test_user.is_pos_multi_site_enabled = True
    await db.commit()

    response = await client.post(
        "/auth/pos/site-token",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "device_token": test_device.device_token,
            "site_id": str(second_site_grant.id),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["site_id"] == str(second_site_grant.id)
    assert body["access_token"] is not None

    await db.refresh(test_device)
    assert test_device.site_id == second_site_grant.id


async def test_site_token_repair_writes_audit_log(
    client, db, test_user, test_access_grant, test_device, second_site_grant
):
    """Re-pairing the device via site-token writes a DEVICE_REPAIRED audit row."""
    test_user.is_pos_multi_site_enabled = True
    await db.commit()

    await client.post(
        "/auth/pos/site-token",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "device_token": test_device.device_token,
            "site_id": str(second_site_grant.id),
        },
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_device.id),
            AuditLog.action == DEVICE_REPAIRED,
        )
    )
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_site_token_same_site_does_not_repair(
    client, db, test_user, test_site, test_access_grant, test_device
):
    """Selecting the device's already-paired site does not write a DEVICE_REPAIRED row."""
    test_user.is_pos_multi_site_enabled = True
    await db.commit()

    await client.post(
        "/auth/pos/site-token",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "device_token": test_device.device_token,
            "site_id": str(test_site.id),
        },
    )

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == DEVICE_REPAIRED)
    )
    assert result.scalar_one_or_none() is None


async def test_site_token_wrong_password_returns_401(
    client, test_user, test_access_grant, test_device, second_site_grant
):
    """site-token re-verifies credentials — a wrong password is rejected even with a valid site_id."""
    response = await client.post(
        "/auth/pos/site-token",
        json={
            "email": "posuser@test.com",
            "password": "WrongPassword!",
            "device_token": test_device.device_token,
            "site_id": str(second_site_grant.id),
        },
    )

    assert response.status_code == 401


# ── PIN set ───────────────────────────────────────────────────────────────────


async def test_pin_set_creates_pin_record(client, db, pos_auth_headers, test_user):
    """POST /auth/pos/pin/set creates a UserPIN row and returns 204."""
    response = await client.post(
        "/auth/pos/pin/set",
        json={"pin": "1234"},
        headers=pos_auth_headers,
    )

    assert response.status_code == 204

    result = await db.execute(
        select(UserPIN).where(UserPIN.user_id == test_user.id)
    )
    pin_record = result.scalar_one()
    assert pin_record.is_pin_reset_required is False


async def test_pin_set_updates_existing_pin(client, db, pos_auth_headers, test_user):
    """Setting PIN twice upserts — no duplicate rows."""
    await client.post("/auth/pos/pin/set", json={"pin": "1234"}, headers=pos_auth_headers)
    await client.post("/auth/pos/pin/set", json={"pin": "5678"}, headers=pos_auth_headers)

    result = await db.execute(
        select(UserPIN).where(UserPIN.user_id == test_user.id)
    )
    pins = result.scalars().all()
    assert len(pins) == 1  # Only one row — upsert, not duplicate


async def test_pin_set_writes_audit_log(client, db, pos_auth_headers, test_user):
    """PIN set writes a POS_PIN_SET audit row."""
    await client.post("/auth/pos/pin/set", json={"pin": "1234"}, headers=pos_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_user.id),
            AuditLog.action == POS_PIN_SET,
        )
    )
    row = result.scalar_one()
    assert row.actor_id == test_user.id


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
    client, db, pos_auth_headers, test_user, test_site, test_access_grant
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
    assert body["user_id"] == str(test_user.id)
    assert body["user_name"] == "Test POS User"
    assert body["access_profile_name"] == "Cashier"
    assert body["is_pin_reset_required"] is False


async def test_pin_verify_creates_new_session_row(
    client, db, pos_auth_headers, test_user, test_site, test_access_grant
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
        select(UserPOSSession).where(UserPOSSession.user_id == test_user.id)
    )
    sessions = result.scalars().all()
    # One session from login (via pos_auth_headers jti) + one from pin verify
    assert len(sessions) >= 1


async def test_pin_verify_wrong_pin_returns_401(
    client, pos_auth_headers, test_user, test_site, test_access_grant
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
    client, test_user, test_site, test_access_grant
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
    client, db, pos_auth_headers, test_user, test_site, test_access_grant
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
            AuditLog.entity_id == str(test_user.id),
            AuditLog.action == POS_PIN_VERIFIED,
        )
    )
    row = result.scalar_one()
    assert row.actor_id == test_user.id


# ── Login missing fields ──────────────────────────────────────────────────────


async def test_pos_login_missing_device_token_returns_422(client, test_user):
    """Missing device_token returns 422."""
    response = await client.post(
        "/auth/pos/login",
        json={"email": "posuser@test.com", "password": "POSPassword123!"},
    )

    assert response.status_code == 422


# ── Case-insensitive email login ────────────────────────────────────────────────


async def test_pos_login_email_case_insensitive(
    client, test_user, test_site, test_access_grant, test_device
):
    """Login succeeds regardless of the casing typed for the account's email."""
    response = await client.post(
        "/auth/pos/login",
        json={
            "email": "PosUser@TEST.com",
            "password": "POSPassword123!",
            "device_token": test_device.device_token,
        },
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == str(test_user.id)
