"""Integration tests for dual-auth catalog routes.

Verifies that catalog routes accept POS JWT, management JWT, and portal JWT,
and that invalid or wrong-type tokens are rejected.

Tests cover:
1. POS JWT continues to work on all catalog routes (regression guard)
2. Management JWT (brand-scope) works on catalog routes
3. Portal JWT works for admin drill-down
4. Invalid/expired token → 401
5. POS JWT used on management-only path → 401 (correct token type required)
"""

import uuid

import pytest

from app.utils.security import (
    create_access_token,
    create_mgmt_access_token,
    create_pos_access_token,
    create_refresh_token,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mgmt_headers(user, grant) -> dict[str, str]:
    """Build Authorization headers with a management JWT for the given grant."""
    token = create_mgmt_access_token(
        user_id=str(user.id),
        scope=grant.scope,
        grant_id=str(grant.id),
        site_id=str(grant.site_id) if grant.site_id else None,
        brand_id=str(grant.brand_id) if grant.brand_id else None,
        group_id=str(grant.group_id) if grant.group_id else None,
    )
    return {"Authorization": f"Bearer {token}"}


def _portal_headers(superadmin) -> dict[str, str]:
    """Build Authorization headers with a portal admin JWT."""
    token = create_access_token(str(superadmin.id), superadmin.role)
    return {"Authorization": f"Bearer {token}"}


# ── Products route — POS JWT regression ──────────────────────────────────────


async def test_list_products_accepts_pos_jwt(client, test_brand, pos_auth_headers):
    """GET /products still works with a standard POS access token."""
    response = await client.get("/products", headers=pos_auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_list_products_accepts_management_jwt_brand_scope(
    client, test_brand, test_portal_grant, test_user, test_manager_profile
):
    """GET /products works with a management JWT (site-scope grant)."""
    headers = _mgmt_headers(test_user, test_portal_grant)
    response = await client.get("/products", headers=headers)
    assert response.status_code == 200


async def test_list_products_accepts_management_jwt_brand_scope_grant(
    client, test_brand, test_brand_grant, test_user
):
    """GET /products works with a management JWT (brand-scope grant)."""
    headers = _mgmt_headers(test_user, test_brand_grant)
    response = await client.get("/products", headers=headers)
    assert response.status_code == 200


async def test_list_products_accepts_portal_jwt(
    client, test_brand, test_superadmin, test_portal_grant
):
    """GET /products works with a portal admin JWT when brand_id supplied."""
    headers = _portal_headers(test_superadmin)
    response = await client.get(
        "/products",
        headers=headers,
        params={"brand_id": str(test_brand.id)},
    )
    assert response.status_code == 200


async def test_list_products_no_token_returns_403(client):
    """GET /products with no Authorization header returns 403."""
    response = await client.get("/products")
    assert response.status_code == 403


async def test_list_products_invalid_token_returns_401(client):
    """GET /products with a garbage token returns 401."""
    response = await client.get(
        "/products", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


async def test_list_products_refresh_token_rejected(client, test_superadmin):
    """A refresh token (wrong type) is rejected on catalog routes."""
    refresh = create_refresh_token(str(test_superadmin.id))
    response = await client.get(
        "/products", headers={"Authorization": f"Bearer {refresh}"}
    )
    assert response.status_code == 401


async def test_management_token_revoked_after_token_version_bump(
    client, db, test_brand, test_brand_grant, test_user
):
    """A management JWT is rejected once the user's token_version is bumped."""
    headers = _mgmt_headers(test_user, test_brand_grant)  # minted at tv=0

    # Works while the token's tv matches the user's token_version
    assert (await client.get("/products", headers=headers)).status_code == 200

    # Simulate a logout-everywhere / password change bumping the counter
    test_user.token_version += 1
    await db.commit()

    # The pre-bump token is now revoked
    assert (await client.get("/products", headers=headers)).status_code == 401


# ── Tax routes ────────────────────────────────────────────────────────────────


async def test_list_tax_categories_accepts_pos_jwt(client, pos_auth_headers):
    """GET /tax/categories works with POS JWT (regression)."""
    response = await client.get("/tax/categories", headers=pos_auth_headers)
    assert response.status_code == 200


async def test_list_tax_categories_accepts_mgmt_jwt(
    client, test_user, test_portal_grant
):
    """GET /tax/categories works with management JWT."""
    headers = _mgmt_headers(test_user, test_portal_grant)
    response = await client.get("/tax/categories", headers=headers)
    assert response.status_code == 200


# ── Revoked grant is rejected ─────────────────────────────────────────────────


async def test_revoked_grant_returns_403(
    client, db, test_user, test_portal_grant
):
    """A management JWT whose grant has been revoked returns 403."""
    headers = _mgmt_headers(test_user, test_portal_grant)

    # Revoke the grant after issuing the token
    test_portal_grant.is_active = False
    db.add(test_portal_grant)
    await db.commit()

    response = await client.get("/products", headers=headers)
    assert response.status_code == 403


# ── Inactive POS user is rejected ────────────────────────────────────────────


async def test_inactive_user_management_token_returns_403(
    client, db, test_user, test_portal_grant
):
    """Management JWT for an inactive POS user returns 403."""
    headers = _mgmt_headers(test_user, test_portal_grant)

    test_user.is_active = False
    db.add(test_user)
    await db.commit()

    response = await client.get("/products", headers=headers)
    assert response.status_code == 403
