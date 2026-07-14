"""Integration tests for access grant management routes.

Covers:
1. List grants — site-scope and brand-scope management callers
2. Create grant — scope authority enforcement (happy path + 403 cases)
3. Update grant — access profile change
4. Revoke grant — soft-delete and 404 on missing
5. POS JWT rejected on write routes (403)
6. Portal JWT has full authority
7. Audit log written for create and revoke
8. Stage 17 — role ceiling (cannot grant a level above your own) and the
   Master User profile being unconditionally ungrantable
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    ACCESS_GRANT_BACKEND_ROLE_UPDATED,
    ACCESS_GRANT_CREATED,
    ACCESS_GRANT_REVOKED,
    ACCESS_PROFILE_PORTAL_UPDATED,
)
from app.constants.statuses import SystemAccessProfile
from app.models.access_profile import AccessProfile
from app.models.audit_log import AuditLog
from app.models.brand import Brand
from app.models.group import Group
from app.models.user import User
from app.models.site import Site
from app.models.user_access_grant import UserAccessGrant
from app.utils.security import create_access_token, create_mgmt_access_token


# ── Local helpers ──────────────────────────────────────────────────────────────


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


# ── Local fixtures ─────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def target_user(db: AsyncSession, test_brand: Brand) -> User:
    """
    A second User who is the *target* of grants created in tests.

    Kept separate from test_user (who is the management *actor*).

    Returns:
        User: A saved, active User instance.
    """
    from app.utils.security import hash_password

    user = User(
        id=uuid.uuid4(),
        group_id=test_brand.group_id,
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


@pytest_asyncio.fixture()
async def admin_profile(db: AsyncSession, test_brand: Brand) -> AccessProfile:
    """The system Admin profile for test_brand (seeded by seed_system_profiles)."""
    result = await db.execute(
        select(AccessProfile).where(
            AccessProfile.brand_id == test_brand.id,
            AccessProfile.name == SystemAccessProfile.ADMIN.value,
        )
    )
    return result.scalar_one()


@pytest_asyncio.fixture()
async def staff_profile(db: AsyncSession, test_brand: Brand) -> AccessProfile:
    """The system Staff profile for test_brand (seeded by seed_system_profiles)."""
    result = await db.execute(
        select(AccessProfile).where(
            AccessProfile.brand_id == test_brand.id,
            AccessProfile.name == SystemAccessProfile.STAFF.value,
        )
    )
    return result.scalar_one()


@pytest_asyncio.fixture()
async def master_profile(db: AsyncSession, test_brand: Brand) -> AccessProfile:
    """The system Master User profile for test_brand (seeded by seed_system_profiles)."""
    result = await db.execute(
        select(AccessProfile).where(
            AccessProfile.brand_id == test_brand.id,
            AccessProfile.name == SystemAccessProfile.MASTER.value,
        )
    )
    return result.scalar_one()


@pytest_asyncio.fixture()
async def test_group_grant(
    db: AsyncSession,
    test_user: User,
    test_group: Group,
    test_manager_profile: AccessProfile,
) -> UserAccessGrant:
    """A persisted active group-scope UserAccessGrant for test_user with a Manager profile."""
    grant = UserAccessGrant(
        id=uuid.uuid4(),
        user_id=test_user.id,
        scope="group",
        site_id=None,
        brand_id=None,
        group_id=test_group.id,
        access_profile_id=test_manager_profile.id,
        granted_by_id=None,
        is_active=True,
        backend_role="admin",
    )
    db.add(grant)
    await db.commit()
    await db.refresh(grant)
    return grant


# ── List grants ────────────────────────────────────────────────────────────────


async def test_list_grants_site_scope_management(
    client, db, test_user, test_site, test_portal_grant, test_manager_profile
):
    """Site-scope management user can list grants for their site."""
    headers = _mgmt_headers(test_user, test_portal_grant)
    response = await client.get("/access-grants", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # test_portal_grant is a site-scope grant for test_site; should be returned
    ids = [g["id"] for g in data]
    assert str(test_portal_grant.id) in ids


async def test_list_grants_brand_scope_management(
    client, db, test_user, test_brand, test_brand_grant, test_portal_grant, test_manager_profile
):
    """Brand-scope management user sees all grants within their brand."""
    headers = _mgmt_headers(test_user, test_brand_grant)
    response = await client.get("/access-grants", headers=headers)
    assert response.status_code == 200
    data = response.json()
    # The site-scope test_portal_grant is within test_brand → should appear
    ids = [g["id"] for g in data]
    assert str(test_portal_grant.id) in ids


async def test_list_grants_portal_with_brand_filter(
    client, db, test_superadmin, test_brand, test_portal_grant, test_manager_profile, test_site
):
    """Portal admin can list grants filtered by brand_id."""
    headers = _portal_headers(test_superadmin)
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
    client, db, test_user, test_brand, test_brand_grant, test_manager_profile, test_site, target_user
):
    """Brand-scope management user can create a site-scope grant for a site in their brand."""
    headers = _mgmt_headers(test_user, test_brand_grant)
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
    client, db, test_user, test_site, test_portal_grant, test_manager_profile, target_user
):
    """Site-scope management user cannot create any grant (403)."""
    headers = _mgmt_headers(test_user, test_portal_grant)
    payload = {
        "user_id": str(target_user.id),
        "scope": "site",
        "site_id": str(test_site.id),
        "access_profile_id": str(test_manager_profile.id),
    }
    response = await client.post("/access-grants", headers=headers, json=payload)
    assert response.status_code == 403


async def test_create_grant_brand_scope_cannot_create_brand_grant(
    client, db, test_user, test_brand, test_brand_grant, test_manager_profile, target_user
):
    """Brand-scope management user cannot create brand-scope grants (403)."""
    headers = _mgmt_headers(test_user, test_brand_grant)
    payload = {
        "user_id": str(target_user.id),
        "scope": "brand",
        "brand_id": str(test_brand.id),
        "access_profile_id": str(test_manager_profile.id),
    }
    response = await client.post("/access-grants", headers=headers, json=payload)
    assert response.status_code == 403


async def test_create_grant_portal_has_full_authority(
    client, db, test_superadmin, test_site, test_manager_profile, target_user
):
    """Portal admin can create any grant regardless of scope."""
    headers = _portal_headers(test_superadmin)
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
    client, db, test_superadmin, test_site, test_manager_profile, target_user
):
    """Creating a second active grant for the same user+scope+entity returns 409."""
    headers = _portal_headers(test_superadmin)
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
    client, db, test_superadmin, test_site, test_manager_profile, target_user
):
    """Creating a grant writes an ACCESS_GRANT_CREATED audit row."""
    headers = _portal_headers(test_superadmin)
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
    client, db, test_superadmin, test_portal_grant, test_manager_profile, test_access_profile
):
    """PATCH /access-grants/{id} updates the access_profile_id."""
    headers = _portal_headers(test_superadmin)
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
    client, db, test_superadmin
):
    """PATCH with a non-existent grant_id returns 404."""
    headers = _portal_headers(test_superadmin)
    response = await client.patch(
        f"/access-grants/{uuid.uuid4()}",
        headers=headers,
        json={"access_profile_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


# ── Revoke grant ───────────────────────────────────────────────────────────────


async def test_revoke_grant_sets_is_active_false(
    client, db, test_superadmin, test_portal_grant, test_manager_profile, test_site
):
    """DELETE /access-grants/{id} soft-deletes the grant (is_active=False)."""
    headers = _portal_headers(test_superadmin)
    response = await client.delete(
        f"/access-grants/{test_portal_grant.id}",
        headers=headers,
    )
    assert response.status_code == 204

    await db.refresh(test_portal_grant)
    assert test_portal_grant.is_active is False


async def test_revoke_grant_writes_audit_log(
    client, db, test_superadmin, test_portal_grant, test_manager_profile
):
    """Revoking a grant writes an ACCESS_GRANT_REVOKED audit row."""
    headers = _portal_headers(test_superadmin)
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
    client, db, test_superadmin
):
    """DELETE with a non-existent grant_id returns 404."""
    headers = _portal_headers(test_superadmin)
    response = await client.delete(
        f"/access-grants/{uuid.uuid4()}",
        headers=headers,
    )
    assert response.status_code == 404


async def test_revoke_already_revoked_returns_409(
    client, db, test_superadmin, test_portal_grant
):
    """Revoking an already-revoked grant returns 409."""
    headers = _portal_headers(test_superadmin)
    # First revoke
    r1 = await client.delete(f"/access-grants/{test_portal_grant.id}", headers=headers)
    assert r1.status_code == 204
    # Second revoke — already inactive
    r2 = await client.delete(f"/access-grants/{test_portal_grant.id}", headers=headers)
    assert r2.status_code == 409


# ── Stage 17: role ceiling — cannot grant a level above your own ──────────────


async def test_create_grant_brand_scope_manager_cannot_grant_admin(
    client, db, test_user, test_brand_grant, admin_profile, test_site, target_user
):
    """A Manager-profile brand-scope grantor cannot grant a higher-ranked Admin profile."""
    headers = _mgmt_headers(test_user, test_brand_grant)
    payload = {
        "user_id": str(target_user.id),
        "scope": "site",
        "site_id": str(test_site.id),
        "access_profile_id": str(admin_profile.id),
    }
    response = await client.post("/access-grants", headers=headers, json=payload)
    assert response.status_code == 403


async def test_create_grant_brand_scope_manager_can_grant_staff(
    client, db, test_user, test_brand_grant, staff_profile, test_site, target_user
):
    """A Manager-profile grantor can grant a lower-ranked Staff profile."""
    headers = _mgmt_headers(test_user, test_brand_grant)
    payload = {
        "user_id": str(target_user.id),
        "scope": "site",
        "site_id": str(test_site.id),
        "access_profile_id": str(staff_profile.id),
    }
    response = await client.post("/access-grants", headers=headers, json=payload)
    assert response.status_code == 201
    assert response.json()["access_profile_id"] == str(staff_profile.id)


async def test_create_grant_group_scope_manager_cannot_grant_admin(
    client, db, test_user, test_group_grant, admin_profile, test_brand, target_user
):
    """A Manager-profile group-scope grantor cannot grant a higher-ranked Admin profile."""
    headers = _mgmt_headers(test_user, test_group_grant)
    payload = {
        "user_id": str(target_user.id),
        "scope": "brand",
        "brand_id": str(test_brand.id),
        "access_profile_id": str(admin_profile.id),
    }
    response = await client.post("/access-grants", headers=headers, json=payload)
    assert response.status_code == 403


async def test_create_grant_rejects_master_profile_for_management_caller(
    client, db, test_user, test_brand_grant, master_profile, test_site, target_user
):
    """The Master User profile can never be granted through this endpoint."""
    headers = _mgmt_headers(test_user, test_brand_grant)
    payload = {
        "user_id": str(target_user.id),
        "scope": "site",
        "site_id": str(test_site.id),
        "access_profile_id": str(master_profile.id),
    }
    response = await client.post("/access-grants", headers=headers, json=payload)
    assert response.status_code == 403


async def test_create_grant_rejects_master_profile_for_portal_admin(
    client, db, test_superadmin, master_profile, test_site, target_user
):
    """Even a portal admin cannot grant the Master User profile — it is auto-created per site."""
    headers = _portal_headers(test_superadmin)
    payload = {
        "user_id": str(target_user.id),
        "scope": "site",
        "site_id": str(test_site.id),
        "access_profile_id": str(master_profile.id),
    }
    response = await client.post("/access-grants", headers=headers, json=payload)
    assert response.status_code == 403


async def test_update_grant_brand_scope_manager_cannot_upgrade_to_admin(
    client, db, test_user, test_brand_grant, test_portal_grant, admin_profile
):
    """PATCHing a grant's profile to Admin is rejected for a Manager-ranked grantor."""
    headers = _mgmt_headers(test_user, test_brand_grant)
    response = await client.patch(
        f"/access-grants/{test_portal_grant.id}",
        headers=headers,
        json={"access_profile_id": str(admin_profile.id)},
    )
    assert response.status_code == 403


async def test_update_grant_brand_scope_manager_can_downgrade_to_staff(
    client, db, test_user, test_brand_grant, test_portal_grant, staff_profile
):
    """PATCHing a grant's profile to a lower-ranked Staff profile succeeds."""
    headers = _mgmt_headers(test_user, test_brand_grant)
    response = await client.patch(
        f"/access-grants/{test_portal_grant.id}",
        headers=headers,
        json={"access_profile_id": str(staff_profile.id)},
    )
    assert response.status_code == 200
    assert response.json()["access_profile_id"] == str(staff_profile.id)


async def test_create_grant_role_ceiling_rejection_writes_no_audit_row(
    client, db, test_user, test_brand_grant, admin_profile, test_site, target_user
):
    """A rejected role-ceiling attempt does not write an ACCESS_GRANT_CREATED audit row."""
    headers = _mgmt_headers(test_user, test_brand_grant)
    payload = {
        "user_id": str(target_user.id),
        "scope": "site",
        "site_id": str(test_site.id),
        "access_profile_id": str(admin_profile.id),
    }
    response = await client.post("/access-grants", headers=headers, json=payload)
    assert response.status_code == 403

    audit_r = await db.execute(
        select(AuditLog).where(
            AuditLog.action == ACCESS_GRANT_CREATED,
            AuditLog.entity_type == "user_access_grant",
        )
    )
    assert audit_r.scalar_one_or_none() is None


# ── Stage 17: GET /access-profiles opened to management callers ──────────────
#
# This route used to require a portal JWT only. Stage 17's delegation UI needs
# management callers to see the profiles they may grant (for role-picker
# filtering), so it now accepts management JWTs too — scoped to their own
# brand/group so it can't be used to browse other tenants' profile catalogs.


@pytest_asyncio.fixture()
async def foreign_brand(db: AsyncSession) -> Brand:
    """A Brand under a brand-new, unrelated Group — outside test_brand/test_group's scope."""
    from app.models.group import Group as GroupModel

    group = GroupModel(
        id=uuid.uuid4(),
        name="Foreign Group",
        is_active=True,
        timezone="Australia/Sydney",
        currency="AUD",
        country="AU",
    )
    db.add(group)
    await db.flush()
    brand = Brand(
        id=uuid.uuid4(),
        group_id=group.id,
        name="Foreign Brand",
        is_active=True,
        timezone="Australia/Sydney",
        currency="AUD",
        country="AU",
    )
    db.add(brand)
    await db.commit()
    await db.refresh(brand)
    return brand


async def test_list_access_profiles_brand_scope_within_scope(
    client, db, test_user, test_brand_grant, test_brand
):
    """A brand-scope management caller can list profiles for their own brand."""
    headers = _mgmt_headers(test_user, test_brand_grant)
    response = await client.get("/access-profiles", headers=headers, params={"brand_id": str(test_brand.id)})
    assert response.status_code == 200
    names = {p["name"] for p in response.json()}
    assert SystemAccessProfile.MANAGER.value in names


async def test_list_access_profiles_brand_scope_outside_scope_returns_403(
    client, db, test_user, test_brand_grant, foreign_brand
):
    """A brand-scope management caller cannot list another brand's profiles."""
    headers = _mgmt_headers(test_user, test_brand_grant)
    response = await client.get("/access-profiles", headers=headers, params={"brand_id": str(foreign_brand.id)})
    assert response.status_code == 403


async def test_list_access_profiles_group_scope_within_group(
    client, db, test_user, test_group_grant, test_brand
):
    """A group-scope management caller can list profiles for any brand in their group."""
    headers = _mgmt_headers(test_user, test_group_grant)
    response = await client.get("/access-profiles", headers=headers, params={"brand_id": str(test_brand.id)})
    assert response.status_code == 200


async def test_list_access_profiles_group_scope_outside_group_returns_403(
    client, db, test_user, test_group_grant, foreign_brand
):
    """A group-scope management caller cannot list a brand outside their group."""
    headers = _mgmt_headers(test_user, test_group_grant)
    response = await client.get("/access-profiles", headers=headers, params={"brand_id": str(foreign_brand.id)})
    assert response.status_code == 403


async def test_list_access_profiles_pos_jwt_forbidden(client, db, pos_auth_headers, test_brand):
    """A POS terminal JWT cannot list access profiles."""
    response = await client.get("/access-profiles", headers=pos_auth_headers, params={"brand_id": str(test_brand.id)})
    assert response.status_code == 403


async def test_list_access_profiles_portal_admin_any_brand(client, db, test_superadmin, foreign_brand):
    """Portal admins retain full authority — no scope restriction."""
    headers = _portal_headers(test_superadmin)
    response = await client.get("/access-profiles", headers=headers, params={"brand_id": str(foreign_brand.id)})
    assert response.status_code == 200


# ── List enrichment: user name / username / ref ──────────────────────────────


async def test_list_grants_includes_user_details(
    client, db, test_superadmin, test_user, test_brand, test_portal_grant
):
    """Each listed grant carries the user's name, login email, and ref code."""
    headers = _portal_headers(test_superadmin)
    response = await client.get(
        "/access-grants", headers=headers, params={"brand_id": str(test_brand.id)}
    )
    assert response.status_code == 200
    row = next((g for g in response.json() if g["id"] == str(test_portal_grant.id)), None)
    assert row is not None
    assert row["user_name"] == test_user.name
    assert row["user_email"] == test_user.email
    assert row["user_ref"] == test_user.ref


# ── Regression: updating backend_role must not NameError on _BACKEND_ROLES ────


async def test_update_grant_backend_role_succeeds(
    client, db, test_superadmin, test_user, test_portal_grant
):
    """PATCH backend_role works (regression: _BACKEND_ROLES was undefined in the service)."""
    headers = _portal_headers(test_superadmin)
    response = await client.patch(
        f"/access-grants/{test_portal_grant.id}",
        headers=headers,
        json={"backend_role": "admin"},
    )
    assert response.status_code == 200
    assert response.json()["backend_role"] == "admin"

    audit_r = await db.execute(
        select(AuditLog).where(
            AuditLog.action == ACCESS_GRANT_BACKEND_ROLE_UPDATED,
            AuditLog.entity_id == str(test_portal_grant.id),
        )
    )
    assert audit_r.scalar_one_or_none() is not None


# ── Bulk update / revoke ─────────────────────────────────────────────────────


async def _create_site_grant(client, headers, target_user, test_site, profile) -> str:
    """Create a site-scope grant via the API and return its id."""
    r = await client.post(
        "/access-grants",
        headers=headers,
        json={
            "user_id": str(target_user.id),
            "scope": "site",
            "site_id": str(test_site.id),
            "access_profile_id": str(profile.id),
        },
    )
    assert r.status_code == 201
    return r.json()["id"]


async def test_bulk_update_sets_profile(
    client, db, test_superadmin, test_user, test_site, test_manager_profile,
    test_access_profile, test_portal_grant, target_user,
):
    """Bulk update applies a new access profile to every listed grant + audits each."""
    headers = _portal_headers(test_superadmin)
    gid = await _create_site_grant(client, headers, target_user, test_site, test_manager_profile)

    response = await client.post(
        "/access-grants/bulk-update",
        headers=headers,
        json={
            "grant_ids": [gid, str(test_portal_grant.id)],
            "access_profile_id": str(test_access_profile.id),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body["succeeded"]) == {gid, str(test_portal_grant.id)}
    assert body["errors"] == []

    db.expunge_all()
    for grant_id in (gid, str(test_portal_grant.id)):
        grant = (await db.execute(select(UserAccessGrant).where(UserAccessGrant.id == grant_id))).scalar_one()
        assert grant.access_profile_id == test_access_profile.id
        audit = await db.execute(
            select(AuditLog).where(
                AuditLog.action == ACCESS_PROFILE_PORTAL_UPDATED,
                AuditLog.entity_id == grant_id,
            )
        )
        assert audit.scalar_one_or_none() is not None


async def test_bulk_update_sets_backend_role(
    client, db, test_superadmin, test_user, test_portal_grant
):
    """Bulk update can set the backend role (user has email+password)."""
    headers = _portal_headers(test_superadmin)
    response = await client.post(
        "/access-grants/bulk-update",
        headers=headers,
        json={"grant_ids": [str(test_portal_grant.id)], "backend_role": "reporting"},
    )
    assert response.status_code == 200
    assert response.json()["succeeded"] == [str(test_portal_grant.id)]

    db.expunge_all()
    grant = (await db.execute(select(UserAccessGrant).where(UserAccessGrant.id == test_portal_grant.id))).scalar_one()
    assert grant.backend_role == "reporting"


async def test_bulk_update_no_fields_returns_422(
    client, db, test_superadmin, test_portal_grant
):
    """Bulk update with neither profile nor backend_role is rejected."""
    headers = _portal_headers(test_superadmin)
    response = await client.post(
        "/access-grants/bulk-update",
        headers=headers,
        json={"grant_ids": [str(test_portal_grant.id)]},
    )
    assert response.status_code == 422


async def test_bulk_revoke_grants(
    client, db, test_superadmin, test_site, test_manager_profile, target_user
):
    """Bulk revoke soft-deletes each grant and writes a revoke audit row."""
    headers = _portal_headers(test_superadmin)
    gid = await _create_site_grant(client, headers, target_user, test_site, test_manager_profile)

    response = await client.post(
        "/access-grants/bulk-revoke", headers=headers, json={"grant_ids": [gid]}
    )
    assert response.status_code == 200
    assert response.json()["succeeded"] == [gid]

    db.expunge_all()
    grant = (await db.execute(select(UserAccessGrant).where(UserAccessGrant.id == gid))).scalar_one()
    assert grant.is_active is False
    audit = await db.execute(
        select(AuditLog).where(
            AuditLog.action == ACCESS_GRANT_REVOKED,
            AuditLog.entity_id == gid,
        )
    )
    assert audit.scalar_one_or_none() is not None


async def test_bulk_revoke_partial_reports_missing(
    client, db, test_superadmin, test_site, test_manager_profile, target_user
):
    """A missing grant id is reported in errors while valid ones still revoke."""
    headers = _portal_headers(test_superadmin)
    gid = await _create_site_grant(client, headers, target_user, test_site, test_manager_profile)
    missing = str(uuid.uuid4())

    response = await client.post(
        "/access-grants/bulk-revoke", headers=headers, json={"grant_ids": [gid, missing]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["succeeded"] == [gid]
    assert [e["grant_id"] for e in body["errors"]] == [missing]


async def test_bulk_update_no_token_returns_403(client, test_portal_grant):
    """Bulk update without a token is rejected."""
    response = await client.post(
        "/access-grants/bulk-update",
        json={"grant_ids": [str(test_portal_grant.id)], "backend_role": "admin"},
    )
    assert response.status_code == 403


async def test_bulk_update_pos_jwt_forbidden(client, pos_auth_headers):
    """A POS terminal JWT cannot bulk-update grants (rejected before grant lookup)."""
    response = await client.post(
        "/access-grants/bulk-update",
        headers=pos_auth_headers,
        json={"grant_ids": [str(uuid.uuid4())], "backend_role": "admin"},
    )
    assert response.status_code == 403
