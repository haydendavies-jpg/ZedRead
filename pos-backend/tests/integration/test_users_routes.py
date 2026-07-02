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

from app.models.user import User

pytestmark = pytest.mark.asyncio


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
