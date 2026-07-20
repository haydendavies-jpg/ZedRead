"""Integration tests for /users routes.

Folds in what used to be the separate /portal-users route tests — SuperAdmin
access is a role on User (superadmin_role), not a separate table, so its
CRUD/suspend/activate tests now live here too, exercised via /users.

Covers:
1. Happy path — list/get/create/update return 200/201 with correct shapes
2. Auth failure — no token → 403; Reseller Staff granting/changing
   superadmin_role → 403 (Admin-role only)
3. Invalid input — missing fields → 422, unrecognised superadmin_role → 422
4. Business rule — 409 duplicate/linked-email password conflicts, 400
   self-deactivate, 404 unknown user, 409 already-active/inactive
5. Audit log — every write asserts the correct audit_logs row
6. Regression — GET /users must not 500 when Group-level master users
   (brand_id=NULL) exist in the database. Previously UserOut declared
   brand_id as non-nullable uuid.UUID, which caused a Pydantic validation
   error when serialising these rows and crashed the entire endpoint.
"""

import uuid

import pytest
from sqlalchemy import select

# Master-user credentials required on POST /sites/ since Change 1
_MASTER_CREDS = {"master_email": "owner@userstest.example", "master_password": "TestPass123!"}

from app.constants.audit_actions import (
    USER_CREATED,
    USER_DEACTIVATED,
    USER_PASSWORD_ADMIN_SET,
    USER_REACTIVATED,
    USER_SUPERADMIN_ROLE_UPDATED,
)
from app.models.audit_log import AuditLog
from app.models.user import User
from app.utils.security import create_access_token, hash_password, verify_password

pytestmark = pytest.mark.asyncio


async def _reseller_staff_headers(db, email: str = "reseller-staff@userstest.example") -> dict[str, str]:
    """Create+persist a Reseller Staff portal admin and return its auth header dict."""
    admin = User(
        id=uuid.uuid4(),
        group_id=None,
        brand_id=None,
        email=email,
        password_hash=hash_password("TestPassword123!"),
        name="Reseller Staff Admin",
        superadmin_role="reseller_staff",
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token = create_access_token(str(admin.id), admin.superadmin_role)
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


async def test_get_user_returns_correct_user(client, portal_auth_headers, test_superadmin):
    """GET /users/{id} returns the correct user."""
    response = await client.get(f"/users/{test_superadmin.id}", headers=portal_auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(test_superadmin.id)


async def test_get_unknown_user_returns_404(client, portal_auth_headers):
    """GET /users/{unknown_id} returns 404."""
    response = await client.get(f"/users/{uuid.uuid4()}", headers=portal_auth_headers)
    assert response.status_code == 404


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


# ── Create user: email/password coupling (shared-email flow) ──────────────────


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
            "email": test_superadmin.email,  # already a portal admin's email
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 201
    user_id = response.json()["id"]

    row = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
    # The new user carries the portal admin's exact hash — same credential, no new password.
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


# ── Create/update user: superadmin_role (folded in from /portal-users) ────────


async def test_create_user_with_superadmin_role_returns_201(client, db, portal_auth_headers):
    """POST /users with superadmin_role creates a pure admin-portal row (no brand)."""
    response = await client.post(
        "/users",
        json={
            "brand_id": None,
            "first_name": "New",
            "last_name": "Admin",
            "email": "new-portal-admin@userstest.example",
            "password": "SecurePassword123!",
            "superadmin_role": "admin",
        },
        headers=portal_auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["superadmin_role"] == "admin"
    assert body["brand_id"] is None

    row = (await db.execute(select(User).where(User.id == body["id"]))).scalar_one()
    assert row.group_id is None


async def test_create_user_superadmin_role_requires_email(client, portal_auth_headers):
    """POST /users with superadmin_role set but no email is rejected — no login path otherwise."""
    response = await client.post(
        "/users",
        json={"brand_id": None, "first_name": "No", "last_name": "Email", "superadmin_role": "admin"},
        headers=portal_auth_headers,
    )
    assert response.status_code == 422


async def test_create_user_superadmin_role_short_password_returns_422(client, portal_auth_headers):
    """A superadmin_role row's password must be at least 12 characters, not just 8."""
    response = await client.post(
        "/users",
        json={
            "brand_id": None,
            "first_name": "Short",
            "last_name": "Pass",
            "email": "shortpass-admin@userstest.example",
            "password": "short8ch",
            "superadmin_role": "admin",
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 422


async def test_create_user_invalid_superadmin_role_returns_422(client, portal_auth_headers):
    """POST /users with an unrecognised superadmin_role value returns 422."""
    response = await client.post(
        "/users",
        json={
            "brand_id": None,
            "first_name": "Bad",
            "last_name": "Role",
            "email": "badrole-admin@userstest.example",
            "password": "SecurePassword123!",
            "superadmin_role": "god_mode",
        },
        headers=portal_auth_headers,
    )
    assert response.status_code == 422


async def test_create_user_superadmin_role_reseller_staff_returns_403(client, db):
    """A Reseller Staff (non-Admin) portal admin cannot grant superadmin_role on create."""
    headers = await _reseller_staff_headers(db)
    response = await client.post(
        "/users",
        json={
            "brand_id": None,
            "first_name": "Should",
            "last_name": "Fail",
            "email": "should-fail-admin@userstest.example",
            "password": "SecurePassword123!",
            "superadmin_role": "admin",
        },
        headers=headers,
    )
    assert response.status_code == 403


async def test_update_user_superadmin_role_writes_audit(client, db, portal_auth_headers, test_user):
    """PATCH /users/{id} granting superadmin_role writes a USER_SUPERADMIN_ROLE_UPDATED audit row."""
    # test_user needs an email+password before it can be granted admin-portal access.
    test_user.email = "grant-target@userstest.example"
    test_user.password_hash = hash_password("ExistingPass123!")
    await db.commit()

    response = await client.patch(
        f"/users/{test_user.id}",
        json={"superadmin_role": "reseller_staff"},
        headers=portal_auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["superadmin_role"] == "reseller_staff"

    audit = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_user.id),
            AuditLog.action == USER_SUPERADMIN_ROLE_UPDATED,
        )
    )
    row = audit.scalar_one()  # raises if 0 or 2+ rows
    assert row.after_state["superadmin_role"] == "reseller_staff"


async def test_update_user_superadmin_role_reseller_staff_returns_403(client, db, test_user):
    """A Reseller Staff portal admin cannot change another row's superadmin_role."""
    test_user.email = "grant-target-2@userstest.example"
    test_user.password_hash = hash_password("ExistingPass123!")
    await db.commit()

    headers = await _reseller_staff_headers(db)
    response = await client.patch(
        f"/users/{test_user.id}",
        json={"superadmin_role": "admin"},
        headers=headers,
    )
    assert response.status_code == 403


async def test_update_user_superadmin_role_without_email_returns_409(client, db, test_brand, portal_auth_headers):
    """Granting superadmin_role to a row with no email/password is rejected — no login path."""
    user = User(
        id=uuid.uuid4(),
        group_id=test_brand.group_id,
        brand_id=test_brand.id,
        first_name="No",
        last_name="Creds",
        name="No Creds",
        email=None,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    response = await client.patch(
        f"/users/{user.id}",
        json={"superadmin_role": "admin"},
        headers=portal_auth_headers,
    )
    assert response.status_code == 409


# ── Email-check lookup (drives the create form's skip-password behaviour) ──


async def test_email_check_existing_portal_admin_email(client, portal_auth_headers, test_superadmin):
    """GET /users/email-check reports an existing portal admin email as taken, with a password."""
    response = await client.get(
        "/users/email-check",
        params={"email": test_superadmin.email},
        headers=portal_auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is True
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


# ── Update user: admin-set password ────────────────────────────────────────────


async def test_update_user_password_any_portal_admin_writes_audit(client, db, test_user, portal_auth_headers):
    """Any portal admin can set a user's password; it's hashed and audited, never echoed back."""
    response = await client.patch(
        f"/users/{test_user.id}",
        json={"password": "NewSecretPass123!"},
        headers=portal_auth_headers,
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


async def test_update_user_password_too_short_returns_422(client, portal_auth_headers):
    """A password under 8 characters is rejected."""
    response = await client.patch(
        f"/users/{uuid.uuid4()}",
        json={"password": "short"},
        headers=portal_auth_headers,
    )
    assert response.status_code == 422


async def test_update_user_password_no_email_returns_409(client, db, test_brand, portal_auth_headers):
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

    response = await client.patch(
        f"/users/{user.id}",
        json={"password": "NewSecretPass123!"},
        headers=portal_auth_headers,
    )
    assert response.status_code == 409


# ── Deactivate / reactivate (folded in from /portal-users suspend/activate) ──


async def test_deactivate_self_returns_400(client, portal_auth_headers, test_superadmin):
    """PATCH /users/{own_id}/deactivate returns 400 — cannot deactivate yourself."""
    response = await client.patch(
        f"/users/{test_superadmin.id}/deactivate", headers=portal_auth_headers
    )
    assert response.status_code == 400


async def test_deactivate_then_reactivate_user(client, db, portal_auth_headers, test_user):
    """PATCH /users/{id}/deactivate then POST .../reactivate toggles is_active correctly."""
    r1 = await client.patch(f"/users/{test_user.id}/deactivate", headers=portal_auth_headers)
    assert r1.status_code == 200
    assert r1.json()["is_active"] is False

    audit1 = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_user.id),
            AuditLog.action == USER_DEACTIVATED,
        )
    )
    assert audit1.scalar_one() is not None

    r2 = await client.post(f"/users/{test_user.id}/reactivate", headers=portal_auth_headers)
    assert r2.status_code == 200
    assert r2.json()["is_active"] is True

    audit2 = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_user.id),
            AuditLog.action == USER_REACTIVATED,
        )
    )
    assert audit2.scalar_one() is not None


async def test_reactivate_already_active_user_returns_409(client, portal_auth_headers, test_user):
    """Reactivating an already-active user returns 409."""
    response = await client.post(f"/users/{test_user.id}/reactivate", headers=portal_auth_headers)
    assert response.status_code == 409


async def test_deactivate_unknown_user_returns_404(client, portal_auth_headers):
    """PATCH /users/{unknown_id}/deactivate returns 404."""
    response = await client.patch(f"/users/{uuid.uuid4()}/deactivate", headers=portal_auth_headers)
    assert response.status_code == 404
