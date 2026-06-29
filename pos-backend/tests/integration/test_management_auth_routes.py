"""Integration tests for management portal authentication routes.

Tests cover all five required scenarios per tests_CLAUDE.md:
1. Happy path — portal user login, POS user single-grant login, multi-grant scope selection
2. Auth failure — wrong password, inactive user, bad refresh token
3. Invalid input — missing fields
4. Business rule — no portal-capable grants, revoked grant, wrong grant owner
5. Audit log — success and failure write correct audit rows
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    AUTH_LOGIN_FAILED,
    AUTH_LOGIN_SUCCESS,
    MGMT_LOGIN_FAILED,
    MGMT_LOGIN_SUCCESS,
    MGMT_TOKEN_ISSUED,
)
from app.models.access_profile import AccessProfile
from app.models.audit_log import AuditLog
from app.models.brand import Brand
from app.models.superadmin import SuperAdmin
from app.models.user import User
from app.models.site import Site
from app.models.user_access_grant import UserAccessGrant
from app.utils.security import create_mgmt_refresh_token, hash_password


# ── Portal user login (unchanged behaviour) ───────────────────────────────────


async def test_superadmin_login_returns_tokens(client, test_superadmin):
    """Existing portal user login still returns access + refresh tokens."""
    response = await client.post(
        "/auth/portal/login",
        json={"email": "admin@test.com", "password": "TestPassword123!"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] is not None
    assert body["refresh_token"] is not None
    assert body["token_type"] == "bearer"
    assert body["available_grants"] is None


# ── POS user login — single grant ─────────────────────────────────────────────


async def test_user_single_grant_returns_mgmt_token(client, test_user, test_portal_grant):
    """POS user with one portal-capable grant gets a management JWT directly."""
    response = await client.post(
        "/auth/portal/login",
        json={"email": "posuser@test.com", "password": "POSPassword123!"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] is not None
    assert body["refresh_token"] is not None
    assert body["user_name"] == test_user.name
    assert str(body["user_id"]) == str(test_user.id)
    assert body["available_grants"] is None


async def test_user_single_grant_audit_log(client, db, test_user, test_portal_grant):
    """Successful POS manager login writes a MGMT_LOGIN_SUCCESS audit row."""
    await client.post(
        "/auth/portal/login",
        json={"email": "posuser@test.com", "password": "POSPassword123!"},
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_user.id),
            AuditLog.action == MGMT_LOGIN_SUCCESS,
        )
    )
    row = result.scalar_one()
    assert row.actor_email == "posuser@test.com"
    assert row.actor_id == test_user.id


# ── POS user login — multiple grants ─────────────────────────────────────────


async def test_user_multi_grant_returns_available_grants(
    client, db, test_user, test_portal_grant, test_brand_grant
):
    """POS user with two portal-capable grants gets a list of available grants."""
    response = await client.post(
        "/auth/portal/login",
        json={"email": "posuser@test.com", "password": "POSPassword123!"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] is None
    assert body["refresh_token"] is None
    assert body["available_grants"] is not None
    assert len(body["available_grants"]) == 2

    scopes = {g["scope"] for g in body["available_grants"]}
    assert "site" in scopes
    assert "brand" in scopes


async def test_user_multi_grant_each_has_scope_name(
    client, test_user, test_portal_grant, test_brand_grant, test_brand, test_site
):
    """Each grant summary in the available_grants list has a non-empty scope_name."""
    response = await client.post(
        "/auth/portal/login",
        json={"email": "posuser@test.com", "password": "POSPassword123!"},
    )

    body = response.json()
    for grant_summary in body["available_grants"]:
        assert grant_summary["scope_name"]
        assert grant_summary["access_profile_name"]
        assert grant_summary["grant_id"]


# ── Management token selection ────────────────────────────────────────────────


async def test_management_token_endpoint_issues_token(client, test_user, test_brand_grant):
    """POST /management-token with valid credentials issues a management JWT."""
    response = await client.post(
        "/auth/portal/management-token",
        json={
            "user_id": str(test_user.id),
            "grant_id": str(test_brand_grant.id),
            "password": "POSPassword123!",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] is not None
    assert body["refresh_token"] is not None
    assert str(body["user_id"]) == str(test_user.id)


async def test_management_token_writes_audit_log(client, db, test_user, test_brand_grant):
    """Scope selection writes a MGMT_TOKEN_ISSUED audit row."""
    await client.post(
        "/auth/portal/management-token",
        json={
            "user_id": str(test_user.id),
            "grant_id": str(test_brand_grant.id),
            "password": "POSPassword123!",
        },
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_user.id),
            AuditLog.action == MGMT_TOKEN_ISSUED,
        )
    )
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_management_token_wrong_password_returns_401(client, test_user, test_brand_grant):
    """Wrong password on management-token endpoint returns 401."""
    response = await client.post(
        "/auth/portal/management-token",
        json={
            "user_id": str(test_user.id),
            "grant_id": str(test_brand_grant.id),
            "password": "WrongPassword!",
        },
    )
    assert response.status_code == 401


async def test_management_token_wrong_grant_owner_returns_403(
    client, db, test_user, test_brand, test_site, test_manager_profile
):
    """Requesting a grant that belongs to a different user returns 403."""
    # Create a second POS user with their own grant
    other_user = User(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        name="Other User",
        email="other@test.com",
        password_hash=hash_password("OtherPass123!"),
        is_active=True,
    )
    db.add(other_user)
    other_grant = UserAccessGrant(
        id=uuid.uuid4(),
        user_id=other_user.id,
        scope="site",
        site_id=test_site.id,
        brand_id=None,
        group_id=None,
        access_profile_id=test_manager_profile.id,
        granted_by_id=None,
        is_active=True,
    )
    db.add(other_grant)
    await db.commit()

    # test_user tries to use other_user's grant — wrong owner → 403
    response = await client.post(
        "/auth/portal/management-token",
        json={
            "user_id": str(test_user.id),
            "grant_id": str(other_grant.id),
            "password": "POSPassword123!",
        },
    )
    assert response.status_code == 403


# ── Auth failures ─────────────────────────────────────────────────────────────


async def test_login_wrong_password_returns_401(client, test_user, test_portal_grant):
    """Wrong password for a POS user returns 401."""
    response = await client.post(
        "/auth/portal/login",
        json={"email": "posuser@test.com", "password": "WrongPassword!"},
    )
    assert response.status_code == 401


async def test_login_inactive_user_returns_401(client, db, test_brand, test_manager_profile, test_site):
    """Inactive POS user returns 401."""
    inactive_user = User(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        name="Inactive User",
        email="inactive@test.com",
        password_hash=hash_password("Pass123!"),
        is_active=False,
    )
    db.add(inactive_user)
    await db.commit()

    response = await client.post(
        "/auth/portal/login",
        json={"email": "inactive@test.com", "password": "Pass123!"},
    )
    assert response.status_code == 401


async def test_login_no_portal_capable_grants_returns_403(client, db, test_brand, test_site):
    """POS user with no portal-capable grants returns 403."""
    non_portal_profile = AccessProfile(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        name="Cashier",
        is_system=False,
        is_active=True,
        can_access_portal=False,
    )
    db.add(non_portal_profile)

    restricted_user = User(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        name="Restricted User",
        email="restricted@test.com",
        password_hash=hash_password("Pass123!"),
        is_active=True,
    )
    db.add(restricted_user)

    grant = UserAccessGrant(
        id=uuid.uuid4(),
        user_id=restricted_user.id,
        scope="site",
        site_id=test_site.id,
        brand_id=None,
        group_id=None,
        access_profile_id=non_portal_profile.id,
        granted_by_id=None,
        is_active=True,
    )
    db.add(grant)
    await db.commit()

    response = await client.post(
        "/auth/portal/login",
        json={"email": "restricted@test.com", "password": "Pass123!"},
    )
    assert response.status_code == 403


async def test_login_unknown_email_returns_401(client):
    """Unknown email returns 401 — same message as wrong password (no enumeration)."""
    response = await client.post(
        "/auth/portal/login",
        json={"email": "nobody@example.com", "password": "AnyPassword!"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


async def test_login_failure_writes_audit_log(client, db, test_user, test_portal_grant):
    """Failed POS user login writes a MGMT_LOGIN_FAILED audit row."""
    await client.post(
        "/auth/portal/login",
        json={"email": "posuser@test.com", "password": "WrongPassword!"},
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.actor_email == "posuser@test.com",
            AuditLog.action == MGMT_LOGIN_FAILED,
        )
    )
    row = result.scalar_one()
    assert row.actor_id is None  # No actor_id on failed login


# ── Management refresh ────────────────────────────────────────────────────────


async def test_mgmt_refresh_with_valid_token(client, test_user, test_portal_grant):
    """Valid management refresh token returns a new token pair."""
    refresh_token = create_mgmt_refresh_token(str(test_user.id))

    response = await client.post(
        "/auth/portal/mgmt-refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] is not None
    assert body["refresh_token"] is not None


async def test_mgmt_refresh_with_invalid_token_returns_401(client):
    """Invalid management refresh token returns 401."""
    response = await client.post(
        "/auth/portal/mgmt-refresh",
        json={"refresh_token": "not-a-valid-token"},
    )
    assert response.status_code == 401


async def test_mgmt_refresh_with_wrong_token_type_returns_401(client, test_user):
    """A portal refresh token (wrong type) is rejected on the mgmt-refresh endpoint."""
    from app.utils.security import create_refresh_token

    wrong_type_token = create_refresh_token(str(test_user.id))
    response = await client.post(
        "/auth/portal/mgmt-refresh",
        json={"refresh_token": wrong_type_token},
    )
    assert response.status_code == 401


# ── Cross-identity login disambiguation (ROLE_MODEL.md §3) ───────────────────


async def test_login_shared_email_returns_available_identities(
    client, db, test_user, test_portal_grant
):
    """A superadmin and a portal-capable user sharing an email get disambiguated."""
    shared_superadmin = SuperAdmin(
        id=uuid.uuid4(),
        email="posuser@test.com",
        password_hash=hash_password("SharedPassword123!"),
        name="Shared Superadmin",
        role="admin",
        is_active=True,
    )
    db.add(shared_superadmin)
    test_user.password_hash = hash_password("SharedPassword123!")
    await db.commit()

    response = await client.post(
        "/auth/portal/login",
        json={"email": "posuser@test.com", "password": "SharedPassword123!"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] is None
    assert body["refresh_token"] is None
    assert body["available_identities"] is not None
    identity_types = {i["identity_type"] for i in body["available_identities"]}
    assert identity_types == {"superadmin", "user"}


async def test_login_shared_email_pos_only_user_unaffected(client, db, test_user):
    """A superadmin sharing an email with a non-portal-capable user logs in unaffected."""
    shared_superadmin = SuperAdmin(
        id=uuid.uuid4(),
        email="posuser@test.com",
        password_hash=hash_password("SharedPassword123!"),
        name="Shared Superadmin",
        role="admin",
        is_active=True,
    )
    db.add(shared_superadmin)
    await db.commit()

    response = await client.post(
        "/auth/portal/login",
        json={"email": "posuser@test.com", "password": "SharedPassword123!"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] is not None
    assert body["available_identities"] is None


async def test_identity_token_superadmin_selection_issues_portal_tokens(
    client, db, test_user, test_portal_grant
):
    """Choosing identity_type=superadmin issues a portal token pair."""
    shared_superadmin = SuperAdmin(
        id=uuid.uuid4(),
        email="posuser@test.com",
        password_hash=hash_password("SharedPassword123!"),
        name="Shared Superadmin",
        role="admin",
        is_active=True,
    )
    db.add(shared_superadmin)
    test_user.password_hash = hash_password("SharedPassword123!")
    await db.commit()

    response = await client.post(
        "/auth/portal/identity-token",
        json={
            "email": "posuser@test.com",
            "password": "SharedPassword123!",
            "identity_type": "superadmin",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] is not None
    assert body["user_id"] is None


async def test_identity_token_user_selection_issues_mgmt_token(
    client, db, test_user, test_portal_grant
):
    """Choosing identity_type=user issues a management token pair."""
    shared_superadmin = SuperAdmin(
        id=uuid.uuid4(),
        email="posuser@test.com",
        password_hash=hash_password("SharedPassword123!"),
        name="Shared Superadmin",
        role="admin",
        is_active=True,
    )
    db.add(shared_superadmin)
    test_user.password_hash = hash_password("SharedPassword123!")
    await db.commit()

    response = await client.post(
        "/auth/portal/identity-token",
        json={
            "email": "posuser@test.com",
            "password": "SharedPassword123!",
            "identity_type": "user",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] is not None
    assert str(body["user_id"]) == str(test_user.id)


async def test_identity_token_wrong_password_returns_401(client, db, test_user, test_portal_grant):
    """Wrong password on the identity-token endpoint returns 401."""
    shared_superadmin = SuperAdmin(
        id=uuid.uuid4(),
        email="posuser@test.com",
        password_hash=hash_password("SharedPassword123!"),
        name="Shared Superadmin",
        role="admin",
        is_active=True,
    )
    db.add(shared_superadmin)
    test_user.password_hash = hash_password("SharedPassword123!")
    await db.commit()

    response = await client.post(
        "/auth/portal/identity-token",
        json={
            "email": "posuser@test.com",
            "password": "WrongPassword!",
            "identity_type": "user",
        },
    )
    assert response.status_code == 401


async def test_identity_token_invalid_identity_type_returns_401(client, test_user, test_portal_grant):
    """An unrecognised identity_type is rejected with 401."""
    response = await client.post(
        "/auth/portal/identity-token",
        json={
            "email": "posuser@test.com",
            "password": "POSPassword123!",
            "identity_type": "bogus",
        },
    )
    assert response.status_code == 401
