"""Integration tests for admin impersonation and related features added in Change 1-3.

Covers:
1. POST /groups/ / /brands/ / /sites/ now require master_email + master_password;
   the created master user has the supplied credentials and a default PIN of 1337.
2. POST /admin/master-grant returns the active grant ID for an entity's master user.
3. POST /admin/impersonate returns a mgmt_access JWT with imp_id, imp_email, imp_name.
4. The impersonation JWT carries the correct claims; the audit log records the admin's identity.
5. Shared-email login (same email used as master for two entities) returns available_grants
   with a user_id entry per grant.
"""

import uuid

from sqlalchemy import select

from app.constants.audit_actions import ADMIN_IMPERSONATION_STARTED
from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.user_access_grant import UserAccessGrant
from app.models.user_pin import UserPIN
from app.utils.security import decode_token, verify_password


# ── Credentials propagated to the master user ────────────────────────────────


async def test_create_group_master_user_has_supplied_email(client, db, portal_auth_headers):
    """The master user created by POST /groups/ has the email provided in the payload."""
    response = await client.post(
        "/groups/",
        json={
            "name": "Cred Test Group",
            "master_email": "groupowner@example.com",
            "master_password": "SecurePass1!",
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 201
    group_id = response.json()["id"]

    result = await db.execute(
        select(User).where(
            User.group_id == uuid.UUID(group_id),
            User.is_master_user == True,  # noqa: E712
        )
    )
    master_user = result.scalar_one()
    assert master_user.email == "groupowner@example.com"
    # Password must be stored hashed — verify it against the supplied plaintext
    assert verify_password("SecurePass1!", master_user.password_hash)


# ── Default PIN 1337 seeded for every master user ─────────────────────────────


async def test_create_group_master_user_gets_default_pin(client, db, portal_auth_headers):
    """POST /groups/ seeds a UserPIN row with pin_hash for '1337' for the master user."""
    response = await client.post(
        "/groups/",
        json={
            "name": "PIN Test Group",
            "master_email": "pintest@example.com",
            "master_password": "SecurePass1!",
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 201
    group_id = response.json()["id"]

    user_result = await db.execute(
        select(User).where(
            User.group_id == uuid.UUID(group_id),
            User.is_master_user == True,  # noqa: E712
        )
    )
    master_user = user_result.scalar_one()

    pin_result = await db.execute(
        select(UserPIN).where(UserPIN.user_id == master_user.id)
    )
    user_pin = pin_result.scalar_one()
    # Default PIN must be "1337" — verify the stored hash matches
    assert verify_password("1337", user_pin.pin_hash)
    assert user_pin.is_pin_reset_required is False


# ── GET /admin/master-grant ──────────────────────────────────────────────────


async def test_get_master_grant_returns_grant_id(client, db, portal_auth_headers):
    """GET /admin/master-grant returns the active grant for a group's master user."""
    create_resp = await client.post(
        "/groups/",
        json={
            "name": "Grant Lookup Group",
            "master_email": "grantlookup@example.com",
            "master_password": "SecurePass1!",
        },
        headers=portal_auth_headers,
    )
    assert create_resp.status_code == 201
    group_id = create_resp.json()["id"]

    response = await client.get(
        "/admin/master-grant",
        params={"group_id": group_id},
        headers=portal_auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert "grant_id" in body

    # Verify the returned grant_id really belongs to the group's master user
    grant_result = await db.execute(
        select(UserAccessGrant)
        .join(User, User.id == UserAccessGrant.user_id)
        .where(
            UserAccessGrant.id == uuid.UUID(body["grant_id"]),
            User.group_id == uuid.UUID(group_id),
            User.is_master_user == True,  # noqa: E712
        )
    )
    assert grant_result.scalar_one() is not None


async def test_get_master_grant_no_entity_id_returns_400(client, portal_auth_headers):
    """GET /admin/master-grant with no entity param returns 400."""
    response = await client.get("/admin/master-grant", headers=portal_auth_headers)
    assert response.status_code == 400


async def test_get_master_grant_unknown_group_returns_404(client, portal_auth_headers):
    """GET /admin/master-grant for a non-existent group returns 404."""
    response = await client.get(
        "/admin/master-grant",
        params={"group_id": str(uuid.uuid4())},
        headers=portal_auth_headers,
    )
    assert response.status_code == 404


# ── POST /admin/impersonate ──────────────────────────────────────────────────


async def test_impersonate_returns_token_with_imp_claims(client, db, portal_auth_headers):
    """POST /admin/impersonate returns a mgmt_access JWT with imp_id, imp_email, imp_name."""
    # Create a group so we have a master user and a grant
    create_resp = await client.post(
        "/groups/",
        json={
            "name": "Impersonate Test Group",
            "master_email": "imp@example.com",
            "master_password": "SecurePass1!",
        },
        headers=portal_auth_headers,
    )
    assert create_resp.status_code == 201
    group_id = create_resp.json()["id"]

    grant_resp = await client.get(
        "/admin/master-grant",
        params={"group_id": group_id},
        headers=portal_auth_headers,
    )
    grant_id = grant_resp.json()["grant_id"]

    imp_resp = await client.post(
        "/admin/impersonate",
        json={"grant_id": grant_id},
        headers=portal_auth_headers,
    )
    assert imp_resp.status_code == 200
    body = imp_resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"

    # Decode and verify the extra impersonation claims
    payload = decode_token(body["access_token"], "mgmt_access")
    assert "imp_id" in payload
    assert "imp_email" in payload
    assert "imp_name" in payload
    assert payload["imp_email"] == "admin@test.com"  # the test_superadmin fixture email


async def test_impersonate_writes_audit_log(client, db, portal_auth_headers, test_superadmin):
    """POST /admin/impersonate writes an ADMIN_IMPERSONATION_STARTED audit row."""
    create_resp = await client.post(
        "/groups/",
        json={
            "name": "Audit Impersonate Group",
            "master_email": "auditimp@example.com",
            "master_password": "SecurePass1!",
        },
        headers=portal_auth_headers,
    )
    group_id = create_resp.json()["id"]

    grant_resp = await client.get(
        "/admin/master-grant",
        params={"group_id": group_id},
        headers=portal_auth_headers,
    )
    grant_id = grant_resp.json()["grant_id"]

    await client.post(
        "/admin/impersonate",
        json={"grant_id": grant_id},
        headers=portal_auth_headers,
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == grant_id,
            AuditLog.action == ADMIN_IMPERSONATION_STARTED,
        )
    )
    row = result.scalar_one()
    assert row.actor_id == test_superadmin.id
    assert row.actor_email == test_superadmin.email


async def test_impersonate_unknown_grant_returns_404(client, portal_auth_headers):
    """POST /admin/impersonate with an unknown grant_id returns 404."""
    response = await client.post(
        "/admin/impersonate",
        json={"grant_id": str(uuid.uuid4())},
        headers=portal_auth_headers,
    )
    assert response.status_code == 404


async def test_impersonate_non_master_grant_returns_403(
    client, db, portal_auth_headers, test_user, test_portal_grant
):
    """POST /admin/impersonate with a non-master-user grant returns 403."""
    response = await client.post(
        "/admin/impersonate",
        json={"grant_id": str(test_portal_grant.id)},
        headers=portal_auth_headers,
    )
    assert response.status_code == 403


# ── Shared email across multiple entities (multi-User same email) ─────────────


async def test_shared_email_returns_available_grants_with_user_ids(
    client, db, portal_auth_headers
):
    """Two entities using the same master_email both appear in available_grants on login."""
    # Create two groups with the same master email
    r1 = await client.post(
        "/groups/",
        json={
            "name": "Shared Email Group One",
            "master_email": "shared@example.com",
            "master_password": "SharedPass1!",
        },
        headers=portal_auth_headers,
    )
    assert r1.status_code == 201

    r2 = await client.post(
        "/groups/",
        json={
            "name": "Shared Email Group Two",
            "master_email": "shared@example.com",
            "master_password": "SharedPass1!",
        },
        headers=portal_auth_headers,
    )
    assert r2.status_code == 201

    login_resp = await client.post(
        "/auth/portal/login",
        json={"email": "shared@example.com", "password": "SharedPass1!"},
    )
    assert login_resp.status_code == 200
    body = login_resp.json()

    # Both master users have portal-capable grants — should get the picker
    assert body["available_grants"] is not None
    assert len(body["available_grants"]) == 2

    # Every grant summary must carry a user_id (required for /management-token)
    for g in body["available_grants"]:
        assert "user_id" in g
        assert g["user_id"] is not None
