"""Integration tests for the page-category permission hierarchy routes (ROLE_MODEL.md §4).

Covers:
1. List page permissions — empty for a fresh non-system profile
2. Grant a page — happy path, idempotent re-grant, audit log written
3. Grant an unknown page_key — 422
4. Revoke a granted page — happy path, audit log written
5. Revoke a page that isn't granted — 404
6. POS JWT rejected on all routes — 403
7. Visible-pages resolver — role grant AND license gate (starter plan excludes some pages)
"""

import uuid

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import ACCESS_PROFILE_PAGE_GRANTED, ACCESS_PROFILE_PAGE_REVOKED
from app.models.access_profile import AccessProfile
from app.models.access_profile_page_permission import AccessProfilePagePermission
from app.models.audit_log import AuditLog
from app.models.brand import Brand
from app.models.license import License
from app.models.site import Site
from app.models.user import User
from app.models.user_access_grant import UserAccessGrant
from app.utils.security import create_access_token, create_mgmt_access_token


def _mgmt_headers(user: User, grant: UserAccessGrant) -> dict[str, str]:
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


def _portal_headers(superadmin) -> dict[str, str]:
    """Return portal JWT headers."""
    token = create_access_token(str(superadmin.id), superadmin.role)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture()
async def granted_profile(db: AsyncSession, test_access_profile: AccessProfile) -> AccessProfile:
    """test_access_profile with "products" pre-granted."""
    db.add(
        AccessProfilePagePermission(
            id=uuid.uuid4(),
            access_profile_id=test_access_profile.id,
            page_key="products",
        )
    )
    await db.commit()
    return test_access_profile


# ── List ───────────────────────────────────────────────────────────────────────


async def test_list_page_permissions_empty_for_fresh_profile(
    client, db, test_user, test_portal_grant, test_access_profile
):
    """A fresh non-system profile has no granted pages."""
    headers = _mgmt_headers(test_user, test_portal_grant)
    response = await client.get(f"/access-profiles/{test_access_profile.id}/pages", headers=headers)
    assert response.status_code == 200
    assert response.json()["page_keys"] == []


async def test_list_page_permissions_404_unknown_profile(client, db, test_user, test_portal_grant):
    """Listing pages for a non-existent profile returns 404."""
    headers = _mgmt_headers(test_user, test_portal_grant)
    response = await client.get(f"/access-profiles/{uuid.uuid4()}/pages", headers=headers)
    assert response.status_code == 404


# ── Grant ──────────────────────────────────────────────────────────────────────


async def test_grant_page_happy_path_writes_audit_log(
    client, db, test_user, test_portal_grant, test_access_profile
):
    """Granting a page creates the permission row and an audit log row."""
    headers = _mgmt_headers(test_user, test_portal_grant)
    response = await client.post(
        f"/access-profiles/{test_access_profile.id}/pages",
        headers=headers,
        json={"page_key": "daily_sales"},
    )
    assert response.status_code == 204

    result = await db.execute(
        select(AccessProfilePagePermission).where(
            AccessProfilePagePermission.access_profile_id == test_access_profile.id,
            AccessProfilePagePermission.page_key == "daily_sales",
        )
    )
    assert result.scalar_one_or_none() is not None

    audit_result = await db.execute(
        select(AuditLog).where(AuditLog.action == ACCESS_PROFILE_PAGE_GRANTED)
    )
    audit_row = audit_result.scalar_one_or_none()
    assert audit_row is not None
    assert audit_row.entity_id == f"{test_access_profile.id}:daily_sales"


async def test_grant_page_idempotent(client, db, test_user, test_portal_grant, granted_profile):
    """Re-granting an already-granted page does not error or duplicate."""
    headers = _mgmt_headers(test_user, test_portal_grant)
    response = await client.post(
        f"/access-profiles/{granted_profile.id}/pages",
        headers=headers,
        json={"page_key": "products"},
    )
    assert response.status_code == 204

    result = await db.execute(
        select(AccessProfilePagePermission).where(
            AccessProfilePagePermission.access_profile_id == granted_profile.id,
            AccessProfilePagePermission.page_key == "products",
        )
    )
    assert len(result.scalars().all()) == 1


async def test_grant_page_unknown_page_key_returns_422(
    client, db, test_user, test_portal_grant, test_access_profile
):
    """Granting an unrecognised page_key returns 422."""
    headers = _mgmt_headers(test_user, test_portal_grant)
    response = await client.post(
        f"/access-profiles/{test_access_profile.id}/pages",
        headers=headers,
        json={"page_key": "not_a_real_page"},
    )
    assert response.status_code == 422


async def test_grant_page_rejects_pos_jwt(client, db, pos_auth_headers, test_access_profile):
    """POS terminal JWTs cannot manage page permissions."""
    response = await client.post(
        f"/access-profiles/{test_access_profile.id}/pages",
        headers=pos_auth_headers,
        json={"page_key": "products"},
    )
    assert response.status_code == 403


# ── Revoke ─────────────────────────────────────────────────────────────────────


async def test_revoke_page_happy_path_writes_audit_log(
    client, db, test_user, test_portal_grant, granted_profile
):
    """Revoking a granted page deletes the row and writes an audit log row."""
    headers = _mgmt_headers(test_user, test_portal_grant)
    response = await client.delete(
        f"/access-profiles/{granted_profile.id}/pages/products",
        headers=headers,
    )
    assert response.status_code == 204

    result = await db.execute(
        select(AccessProfilePagePermission).where(
            AccessProfilePagePermission.access_profile_id == granted_profile.id,
            AccessProfilePagePermission.page_key == "products",
        )
    )
    assert result.scalar_one_or_none() is None

    audit_result = await db.execute(
        select(AuditLog).where(AuditLog.action == ACCESS_PROFILE_PAGE_REVOKED)
    )
    assert audit_result.scalar_one_or_none() is not None


async def test_revoke_page_not_granted_returns_404(
    client, db, test_user, test_portal_grant, test_access_profile
):
    """Revoking a page that was never granted returns 404."""
    headers = _mgmt_headers(test_user, test_portal_grant)
    response = await client.delete(
        f"/access-profiles/{test_access_profile.id}/pages/products",
        headers=headers,
    )
    assert response.status_code == 404


# ── Visible pages (role grant AND license gate) ───────────────────────────────


async def test_visible_pages_combines_role_and_license_gate(
    client, db, test_user, test_portal_grant, test_access_profile, test_site, test_license
):
    """A page granted to the role but excluded by the starter license plan is hidden."""
    # Grant both a starter-allowed page and a starter-excluded page to the role
    db.add_all(
        [
            AccessProfilePagePermission(
                id=uuid.uuid4(), access_profile_id=test_access_profile.id, page_key="products"
            ),
            AccessProfilePagePermission(
                id=uuid.uuid4(), access_profile_id=test_access_profile.id, page_key="audit_log"
            ),
        ]
    )
    await db.commit()
    # test_license fixture is plan_name="starter", linked to test_site

    headers = _mgmt_headers(test_user, test_portal_grant)
    response = await client.get(
        f"/access-profiles/{test_access_profile.id}/visible-pages",
        headers=headers,
        params={"site_id": str(test_site.id)},
    )
    assert response.status_code == 200
    page_keys = response.json()["page_keys"]
    assert "products" in page_keys
    assert "audit_log" not in page_keys


# ── Bulk grant/revoke ──────────────────────────────────────────────────────────


async def test_bulk_set_pages_grant_happy_path_writes_audit_logs(
    client, db, test_user, test_portal_grant, test_access_profile
):
    """Bulk-granting multiple pages creates all rows and one audit row per key."""
    headers = _mgmt_headers(test_user, test_portal_grant)
    response = await client.post(
        f"/access-profiles/{test_access_profile.id}/pages/bulk",
        headers=headers,
        json={"page_keys": ["daily_sales", "tax_collected"], "grant": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body["changed"]) == {"daily_sales", "tax_collected"}

    result = await db.execute(
        select(AccessProfilePagePermission.page_key).where(
            AccessProfilePagePermission.access_profile_id == test_access_profile.id,
        )
    )
    assert {row[0] for row in result} == {"daily_sales", "tax_collected"}

    audit_result = await db.execute(
        select(AuditLog).where(AuditLog.action == ACCESS_PROFILE_PAGE_GRANTED)
    )
    assert len(audit_result.scalars().all()) == 2


async def test_bulk_set_pages_grant_is_idempotent(
    client, db, test_user, test_portal_grant, granted_profile
):
    """Bulk-granting a mix of already-granted and new pages only changes the new ones."""
    headers = _mgmt_headers(test_user, test_portal_grant)
    response = await client.post(
        f"/access-profiles/{granted_profile.id}/pages/bulk",
        headers=headers,
        json={"page_keys": ["products", "daily_sales"], "grant": True},
    )
    assert response.status_code == 200
    assert response.json()["changed"] == ["daily_sales"]


async def test_bulk_set_pages_revoke_happy_path(
    client, db, test_user, test_portal_grant, test_access_profile
):
    """Bulk-revoking granted pages removes them and skips ones never granted."""
    db.add_all(
        [
            AccessProfilePagePermission(
                id=uuid.uuid4(), access_profile_id=test_access_profile.id, page_key="products"
            ),
            AccessProfilePagePermission(
                id=uuid.uuid4(), access_profile_id=test_access_profile.id, page_key="daily_sales"
            ),
        ]
    )
    await db.commit()

    headers = _mgmt_headers(test_user, test_portal_grant)
    response = await client.post(
        f"/access-profiles/{test_access_profile.id}/pages/bulk",
        headers=headers,
        json={"page_keys": ["products", "audit_log"], "grant": False},
    )
    assert response.status_code == 200
    # "audit_log" was never granted, so only "products" is actually changed.
    assert response.json()["changed"] == ["products"]

    result = await db.execute(
        select(AccessProfilePagePermission.page_key).where(
            AccessProfilePagePermission.access_profile_id == test_access_profile.id,
        )
    )
    assert {row[0] for row in result} == {"daily_sales"}


async def test_bulk_set_pages_unknown_page_key_returns_422(
    client, db, test_user, test_portal_grant, test_access_profile
):
    """An unrecognised page_key in the batch returns 422 without changing anything."""
    headers = _mgmt_headers(test_user, test_portal_grant)
    response = await client.post(
        f"/access-profiles/{test_access_profile.id}/pages/bulk",
        headers=headers,
        json={"page_keys": ["products", "not_a_real_page"], "grant": True},
    )
    assert response.status_code == 422

    result = await db.execute(
        select(AccessProfilePagePermission).where(
            AccessProfilePagePermission.access_profile_id == test_access_profile.id,
        )
    )
    assert result.scalar_one_or_none() is None


async def test_bulk_set_pages_rejects_pos_jwt(client, db, pos_auth_headers, test_access_profile):
    """POS terminal JWTs cannot bulk-manage page permissions."""
    response = await client.post(
        f"/access-profiles/{test_access_profile.id}/pages/bulk",
        headers=pos_auth_headers,
        json={"page_keys": ["products"], "grant": True},
    )
    assert response.status_code == 403
