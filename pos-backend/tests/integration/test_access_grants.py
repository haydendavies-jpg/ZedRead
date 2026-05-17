"""Integration tests for access grant management routes.

Covers:
1. List grants — site-scope and brand-scope management callers
2. Create grant — scope authority enforcement (happy path + 403 cases)
3. Update grant — access profile change
4. Revoke grant — soft-delete and 404 on missing
5. POS JWT rejected on write routes (403)
6. Portal JWT has full authority
7. Audit log written for create and revoke
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import ACCESS_GRANT_CREATED, ACCESS_GRANT_REVOKED
from app.models.access_profile import AccessProfile
from app.models.audit_log import AuditLog
from app.models.brand import Brand
from app.models.pos_user import POSUser
from app.models.site import Site
from app.models.user_access_grant import UserAccessGrant
from app.utils.security import create_access_token, create_mgmt_access_token


# ── Local helpers ──────────────────────────────────────────────────────────────


def _mgmt_headers(user: POSUser, grant: UserAccessGrant) -> dict[str, str]:
    """Return management JWT headers for the given user+grant pair."""
    token = create_mgmt_access_token(
        user_id=str(user.id),
        scope=grant.scope,
        grant_id=str(grant.id),
        site_id=str(grant.site_id) if grant.site_id else None,
        brand_id=str(grant.brand_id) if grant.brand_id else None,
        group_id=str(grant.group_id) if grant.group_id else None,
    )
    return {"Authorization": f"Bearer {token}"}


def _portal_headers(portal_user) -> dict[str, str]:
    """Return portal JWT headers."""
    token = create_access_token(str(portal_user.id), portal_user.role)
    return {"Authorization": f"Bearer {token}"}


# ── Local fixtures ─────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def target_user(db: AsyncSession, test_brand: Brand) -> POSUser:
    """
    A second POSUser who is the *target* of grants created in tests.

    Kept separate from test_pos_user (who is the management *actor*).

    Returns:
        POSUser: A saved, active POSUser instance.
    """
    from app.utils.security import hash_password

    user = POSUser(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        name="Target User",
        email="target@test.com",
        password_hash=hash_password("TargetPassword123!"),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ── List grants ────────────────────────────────────────────────────────────────


async def test_list_grants_site_scope_management(
    client, db, test_pos_user, test_site, test_portal_grant, test_manager_profile
):
    """Site-scope management user can list grants for their site."""
    headers = _mgmt_headers(test_pos_user, test_portal_grant)
    response = await client.get("/access-grants", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # test_portal_grant is a site-scope grant for test_site; should be returned
    ids = [g["id"] for g in data]
    assert str(test_portal_grant.id) in ids


async def test_list_grants_brand_scope_management(
    client, db, test_pos_user, test_brand, test_brand_grant, test_portal_grant, test_manager_profile
):
    """Brand-scope management user sees all grants within their brand."""
    headers = _mgmt_headers(test_pos_user, test_brand_grant)
    response = await client.get("/access-grants", headers=headers)
    assert response.status_code == 200
    data = response.json()
    # The site-scope test_portal_grant is within test_brand → should appear
    ids = [g["id"] for g in data]
    assert str(test_portal_grant.id) in ids


async def test_list_grants_portal_with_brand_filter(
    client, db, test_portal_user, test_brand, test_portal_grant, test_manager_profile, test_site
):
    """Portal admin can list grants filtered by brand_id."""
    headers = _portal_headers(test_portal_user)
    response = await client.get(
        "/access-grants",
        headers=headers,
        params={"brand_id": str(test_brand.id)},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_list_grants_no_token_returns_403(client):
    """No Authorization header → 403."""
    response = await client.get("/access-grants")
    assert response.status_code == 403


# ── Create grant ───────────────────────────────────────────────────────────────


async def test_create_grant_brand_scope_creates_site_grant(
    client, db, test_pos_user, test_brand, test_brand_grant, test_manager_profile, test_site, target_user
):
    """Brand-scope management user can create a site-scope grant for a site in their brand."""
    headers = _mgmt_headers(test_pos_user, test_brand_grant)
    payload = {
        "user_id": str(target_user.id),
        "scope": "site",
        "site_id": str(test_site.id),
        "access_profile_id": str(test_manager_profile.id),
    }
    response = await client.post("/access-grants", headers=headers, json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["scope"] == "site"
    assert data["site_id"] == str(test_site.id)
    assert data["user_id"] == str(target_user.id)


async def test_create_grant_site_scope_forbidden(
    client, db, test_pos_user, test_site, test_portal_grant, test_manager_profile, target_user
):
    """Site-scope management user cannot create any grant (403)."""
    headers = _mgmt_headers(test_pos_user, test_portal_grant)
    payload = {
        "user_id": str(target_user.id),
        "scope": "site",
        "site_id": str(test_site.id),
        "access_profile_id": str(test_manager_profile.id),
    }
    response = await client.post("/access-grants", headers=headers, json=payload)
    assert response.status_code == 403


async def test_create_grant_brand_scope_cannot_create_brand_grant(
    client, db, test_pos_user, test_brand, test_brand_grant, test_manager_profile, target_user
):
    """Brand-scope management user cannot create brand-scope grants (403)."""
    headers = _mgmt_headers(test_pos_user, test_brand_grant)
    payload = {
        "user_id": str(target_user.id),
        "scope": "brand",
        "brand_id": str(test_brand.id),
        "access_profile_id": str(test_manager_profile.id),
    }
    response = await client.post("/access-grants", headers=headers, json=payload)
    assert response.status_code == 403


async def test_create_grant_portal_has_full_authority(
    client, db, test_portal_user, test_site, test_manager_profile, target_user
):
    """Portal admin can create any grant regardless of scope."""
    headers = _portal_headers(test_portal_user)
    payload = {
        "user_id": str(target_user.id),
        "scope": "site",
        "site_id": str(test_site.id),
        "access_profile_id": str(test_manager_profile.id),
    }
    response = await client.post("/access-grants", headers=headers, json=payload)
    assert response.status_code == 201


async def test_create_grant_pos_jwt_forbidden(
    client, db, pos_auth_headers, test_site, test_manager_profile, target_user
):
    """POS terminal JWT cannot create grants (403)."""
    payload = {
        "user_id": str(target_user.id),
        "scope": "site",
        "site_id": str(test_site.id),
        "access_profile_id": str(test_manager_profile.id),
    }
    response = await client.post("/access-grants", headers=pos_auth_headers, json=payload)
    assert response.status_code == 403


async def test_create_grant_duplicate_returns_409(
    client, db, test_portal_user, test_site, test_manager_profile, target_user
):
    """Creating a second active grant for the same user+scope+entity returns 409."""
    headers = _portal_headers(test_portal_user)
    payload = {
        "user_id": str(target_user.id),
        "scope": "site",
        "site_id": str(test_site.id),
        "access_profile_id": str(test_manager_profile.id),
    }
    r1 = await client.post("/access-grants", headers=headers, json=payload)
    assert r1.status_code == 201
    r2 = await client.post("/access-grants", headers=headers, json=payload)
    assert r2.status_code == 409


async def test_create_grant_writes_audit_log(
    client, db, test_portal_user, test_site, test_manager_profile, target_user
):
    """Creating a grant writes an ACCESS_GRANT_CREATED audit row."""
    headers = _portal_headers(test_portal_user)
    payload = {
        "user_id": str(target_user.id),
        "scope": "site",
        "site_id": str(test_site.id),
        "access_profile_id": str(test_manager_profile.id),
    }
    response = await client.post("/access-grants", headers=headers, json=payload)
    assert response.status_code == 201

    grant_id = response.json()["id"]
    audit_r = await db.execute(
        select(AuditLog).where(
            AuditLog.action == ACCESS_GRANT_CREATED,
            AuditLog.entity_id == grant_id,
        )
    )
    audit = audit_r.scalar_one_or_none()
    assert audit is not None


# ── Update grant ───────────────────────────────────────────────────────────────


async def test_update_grant_changes_access_profile(
    client, db, test_portal_user, test_portal_grant, test_manager_profile, test_access_profile
):
    """PATCH /access-grants/{id} updates the access_profile_id."""
    headers = _portal_headers(test_portal_user)
    # Create a second profile to switch to
    new_profile = AccessProfile(
        id=uuid.uuid4(),
        brand_id=test_access_profile.brand_id,
        name="Supervisor",
        is_system=False,
        is_active=True,
        can_access_portal=False,
    )
    db.add(new_profile)
    await db.commit()

    response = await client.patch(
        f"/access-grants/{test_portal_grant.id}",
        headers=headers,
        json={"access_profile_id": str(new_profile.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["access_profile_id"] == str(new_profile.id)


async def test_update_grant_pos_jwt_forbidden(
    client, db, pos_auth_headers, test_manager_profile
):
    """POS JWT cannot update grants (403 before any grant lookup)."""
    response = await client.patch(
        f"/access-grants/{uuid.uuid4()}",
        headers=pos_auth_headers,
        json={"access_profile_id": str(test_manager_profile.id)},
    )
    assert response.status_code == 403


async def test_update_grant_not_found_returns_404(
    client, db, test_portal_user
):
    """PATCH with a non-existent grant_id returns 404."""
    headers = _portal_headers(test_portal_user)
    response = await client.patch(
        f"/access-grants/{uuid.uuid4()}",
        headers=headers,
        json={"access_profile_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


# ── Revoke grant ───────────────────────────────────────────────────────────────


async def test_revoke_grant_sets_is_active_false(
    client, db, test_portal_user, test_portal_grant, test_manager_profile, test_site
):
    """DELETE /access-grants/{id} soft-deletes the grant (is_active=False)."""
    headers = _portal_headers(test_portal_user)
    response = await client.delete(
        f"/access-grants/{test_portal_grant.id}",
        headers=headers,
    )
    assert response.status_code == 204

    await db.refresh(test_portal_grant)
    assert test_portal_grant.is_active is False


async def test_revoke_grant_writes_audit_log(
    client, db, test_portal_user, test_portal_grant, test_manager_profile
):
    """Revoking a grant writes an ACCESS_GRANT_REVOKED audit row."""
    headers = _portal_headers(test_portal_user)
    await client.delete(f"/access-grants/{test_portal_grant.id}", headers=headers)

    audit_r = await db.execute(
        select(AuditLog).where(
            AuditLog.action == ACCESS_GRANT_REVOKED,
            AuditLog.entity_id == str(test_portal_grant.id),
        )
    )
    audit = audit_r.scalar_one_or_none()
    assert audit is not None


async def test_revoke_grant_pos_jwt_forbidden(
    client, db, pos_auth_headers
):
    """POS JWT cannot revoke grants (403 before any grant lookup)."""
    response = await client.delete(
        f"/access-grants/{uuid.uuid4()}",
        headers=pos_auth_headers,
    )
    assert response.status_code == 403


async def test_revoke_grant_not_found_returns_404(
    client, db, test_portal_user
):
    """DELETE with a non-existent grant_id returns 404."""
    headers = _portal_headers(test_portal_user)
    response = await client.delete(
        f"/access-grants/{uuid.uuid4()}",
        headers=headers,
    )
    assert response.status_code == 404


async def test_revoke_already_revoked_returns_409(
    client, db, test_portal_user, test_portal_grant
):
    """Revoking an already-revoked grant returns 409."""
    headers = _portal_headers(test_portal_user)
    # First revoke
    r1 = await client.delete(f"/access-grants/{test_portal_grant.id}", headers=headers)
    assert r1.status_code == 204
    # Second revoke — already inactive
    r2 = await client.delete(f"/access-grants/{test_portal_grant.id}", headers=headers)
    assert r2.status_code == 409
