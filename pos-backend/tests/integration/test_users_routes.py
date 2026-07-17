"""Integration tests for /users routes.

Covers:
1. Happy path — list returns 200 with correct shape
2. Auth failure — no token → 403
3. Regression — GET /users must not 500 when Group-level master users
   (brand_id=NULL) exist in the database. Previously UserOut declared
   brand_id as non-nullable uuid.UUID, which caused a Pydantic validation
   error when serialising these rows and crashed the entire endpoint.
"""

import uuid

import pytest
from sqlalchemy import select

# Master-user credentials required on POST /sites/ since Change 1
_MASTER_CREDS = {"master_email": "owner@userstest.example", "master_password": "TestPass123!"}

from app.constants.audit_actions import USER_CREATED, USER_PASSWORD_ADMIN_SET
from app.models.audit_log import AuditLog
from app.models.superadmin import SuperAdmin
from app.models.user import User
from app.utils.security import create_access_token, hash_password, verify_password

pytestmark = pytest.mark.asyncio


async def _headers_for_email(db, email: str) -> dict[str, str]:
    """Create+persist a SuperAdmin with the given email and return its auth header dict."""
    admin = SuperAdmin(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("TestPassword123!"),
        name="Gated Admin",
        role="admin",
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token = create_access_token(str(admin.id), admin.role)
    return {"Authorization": f"Bearer {token}"}


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_list_users_returns_200(client, portal_auth_headers, test_group):
    """GET /users returns 200 with an empty list when no users exist."""
    response = await client.get("/users", headers=portal_auth_headers)

    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_list_users_no_token_returns_403(client):
    """GET /users without a token returns 403."""
    response = await client.get("/users")
    assert response.status_code == 403


# ── Regression: brand_id=NULL (Group master user) must not crash GET /users ──


async def test_list_users_with_group_master_user_returns_200(
    client, db, portal_auth_headers, test_group
):
    """GET /users returns 200 even when a Group-scoped master user (brand_id=NULL) exists.

    Regression test for the bug where UserOut.brand_id was declared as
    non-nullable (uuid.UUID), causing a Pydantic validation error and a 500
    response whenever a Group-level master user appeared in the result set.
    The fix makes brand_id Optional (uuid.UUID | None = None).
    """
    # Create a Group-level master user with brand_id=NULL — this is the
    # exact shape _create_group_master_user() produces in group_service.py.
    group_master = User(
        id=uuid.uuid4(),
        group_id=test_group.id,
        brand_id=None,  # NULL — this is the field that previously caused the 500
        name=test_group.name,
        email=f"master-{test_group.id}@system.zedread.internal",
        is_master_user=True,
        is_active=True,
    )
    db.add(group_master)
    await db.commit()

    # Before the fix this returned 500 due to Pydantic rejecting brand_id=None.
    response = await client.get("/users", headers=portal_auth_headers)

    assert response.status_code == 200
    users = response.json()

    # The master user must appear in the response with brand_id=null
    master_out = next((u for u in users if u["id"] == str(group_master.id)), None)
    assert master_out is not None, "Group master user missing from /users response"
    assert master_out["brand_id"] is None


async def test_create_site_creates_site_master_user_visible_in_list(
    client, db, portal_auth_headers, test_brand
):
    """Creating a site via POST /sites auto-creates a Site master user that
    is visible via GET /users.

    This is the end-to-end reproduction of the original bug report:
    'when creating a site a POS user for that site is not added as the
    sites master user' — the master user WAS created correctly, but the
    GET /users endpoint crashed (500) because a Group master user with
    brand_id=NULL was present and the old UserOut schema rejected None.
    After the fix, GET /users returns 200 and the Site master user is visible.
    """
    # POST /sites triggers _create_master_user() inside the same transaction,
    # which also calls _create_group_master_user() for the Group if needed.
    response = await client.post(
        "/sites/",
        json={
            "brand_id": str(test_brand.id),
            "name": "Regression Site",
            "timezone": "Australia/Sydney",
            "currency": "AUD",
            "country": "AU",
            "address_street": "1 Test St",
            "address_state": "NSW",
            "address_postcode": "2000",
            **_MASTER_CREDS,
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 201
    site_id = response.json()["id"]

    # GET /users must return 200 (not 500) and include the site's master user
    list_response = await client.get("/users", headers=portal_auth_headers)
    assert list_response.status_code == 200

    users = list_response.json()
    # Find the master user for this site by the email supplied at creation time
    master = next(
        (u for u in users if u.get("email") == _MASTER_CREDS["master_email"]),
        None,
    )
    assert master is not None, (
        f"Site master user for site {site_id} not found in GET /users response. "
        f"Users returned: {[u.get('email') for u in users]}"
    )


# ── Create user: email/password coupling (ROLE_MODEL.md §3 shared-email flow) ──


async def test_create_user_new_email_requires_password(client, portal_auth_headers, test_brand):
    """A brand-new email with no password is rejected — the login would be unusable."""
    response = await client.post(
        "/users",
        json={
            "brand_id": str(test_brand.id),
            "first_name": "Fresh",
            "last_name": "Person",
            "email": "fresh-unique@userstest.example",
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 422


async def test_create_user_new_email_with_password_writes_audit(
    client, db, portal_auth_headers, test_brand
):
    """A new email + password creates the user and writes the USER_CREATED audit row."""
    response = await client.post(
        "/users",
        json={
            "brand_id": str(test_brand.id),
            "first_name": "Brand",
            "last_name": "New",
            "email": "brandnew-unique@userstest.example",
            "password": "SecretPass123!",
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 201
    user_id = response.json()["id"]

    audit = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == user_id,
            AuditLog.action == USER_CREATED,
        )
    )
    assert audit.scalar_one() is not None  # raises if 0 or 2+ rows


async def test_create_user_shared_email_links_existing_password(
    client, db, portal_auth_headers, test_brand, test_superadmin
):
    """A new user on an already-registered email reuses that identity's password, no new one given."""
    response = await client.post(
        "/users",
        json={
            "brand_id": str(test_brand.id),
            "first_name": "Shared",
            "last_name": "Owner",
            "email": test_superadmin.email,  # already a SuperAdmin's email
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 201
    user_id = response.json()["id"]

    row = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
    # The new user carries the SuperAdmin's exact hash — same credential, no new password.
    assert row.password_hash == test_superadmin.password_hash
    assert verify_password("TestPassword123!", row.password_hash)


async def test_create_user_shared_email_rejects_new_password(
    client, portal_auth_headers, test_brand, test_superadmin
):
    """Supplying a fresh password for an already-registered email is rejected (409)."""
    response = await client.post(
        "/users",
        json={
            "brand_id": str(test_brand.id),
            "first_name": "Shared",
            "last_name": "Owner",
            "email": test_superadmin.email,
            "password": "DifferentPass123!",
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 409


# ── Email-check lookup (drives the create form's skip-password behaviour) ──


async def test_email_check_existing_superadmin_email(client, portal_auth_headers, test_superadmin):
    """GET /users/email-check reports an existing SuperAdmin email as taken, with a password."""
    response = await client.get(
        "/users/email-check",
        params={"email": test_superadmin.email},
        headers=portal_auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is True
    assert data["identity_type"] == "superadmin"
    assert data["has_password"] is True


async def test_email_check_unknown_email(client, portal_auth_headers):
    """GET /users/email-check reports an unregistered email as available."""
    response = await client.get(
        "/users/email-check",
        params={"email": "nobody-unique@userstest.example"},
        headers=portal_auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["exists"] is False


async def test_email_check_no_token_returns_403(client):
    """GET /users/email-check without a token returns 403."""
    response = await client.get("/users/email-check", params={"email": "x@y.example"})
    assert response.status_code == 403


# ── Update user: admin-set password (temporary single-admin gate) ──────────────


async def test_update_user_password_allowed_admin_writes_audit(client, db, test_user):
    """The gated SuperAdmin can set a user's password; it's hashed and audited, never echoed back."""
    headers = await _headers_for_email(db, "hayden_davies@live.com.au")

    response = await client.patch(
        f"/users/{test_user.id}",
        json={"password": "NewSecretPass123!"},
        headers=headers,
    )

    assert response.status_code == 200
    assert "password" not in response.json()

    row = (await db.execute(select(User).where(User.id == test_user.id))).scalar_one()
    assert verify_password("NewSecretPass123!", row.password_hash)

    audit = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_user.id),
            AuditLog.action == USER_PASSWORD_ADMIN_SET,
        )
    )
    assert audit.scalar_one() is not None  # raises if 0 or 2+ rows


async def test_update_user_password_other_admin_returns_403(client, db, test_user, portal_auth_headers):
    """Any SuperAdmin other than the gated one is rejected with 403, and the password is unchanged."""
    original_hash = test_user.password_hash

    response = await client.patch(
        f"/users/{test_user.id}",
        json={"password": "NewSecretPass123!"},
        headers=portal_auth_headers,
    )

    assert response.status_code == 403

    row = (await db.execute(select(User).where(User.id == test_user.id))).scalar_one()
    assert row.password_hash == original_hash


async def test_update_user_password_too_short_returns_422(client, db):
    """A password under 8 characters is rejected before the gate check runs."""
    headers = await _headers_for_email(db, "hayden_davies@live.com.au")

    response = await client.patch(
        f"/users/{uuid.uuid4()}",
        json={"password": "short"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_update_user_password_no_email_returns_409(client, db, test_brand):
    """Setting a password on a User with no email yet is rejected — it would be unusable."""
    user = User(
        id=uuid.uuid4(),
        group_id=test_brand.group_id,
        brand_id=test_brand.id,
        name="No Email User",
        email=None,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    headers = await _headers_for_email(db, "hayden_davies@live.com.au")
    response = await client.patch(
        f"/users/{user.id}",
        json={"password": "NewSecretPass123!"},
        headers=headers,
    )
    assert response.status_code == 409
