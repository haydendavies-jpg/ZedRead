"""Integration tests for the POS settings framework (Android POS Phase 2).

Covers:
1. Happy path — GET /settings resolves catalog + brand/site override state;
   GET /pos/settings resolves for a terminal's own site
2. Auth failure — no token; POS terminal forbidden from management writes
3. Invalid input — unknown setting key, bad type/option value
4. Business rules — permission-gated ("site_settings" page), site-scope
   caller pinned to their own site, portal admin always permitted
5. Audit log — update and reset both write correct rows
"""

import uuid

import pytest
from sqlalchemy import select

from app.constants.audit_actions import SETTING_RESET, SETTING_UPDATED
from app.models.access_profile_page_permission import AccessProfilePagePermission
from app.models.audit_log import AuditLog

pytestmark = pytest.mark.asyncio


async def _grant_site_settings(db, profile) -> None:
    db.add(
        AccessProfilePagePermission(
            id=uuid.uuid4(), access_profile_id=profile.id, page_key="site_settings"
        )
    )
    await db.flush()


# ── GET /settings ──────────────────────────────────────────────────────────


async def test_list_settings_without_permission_returns_403(client, mgmt_auth_headers):
    """A management caller whose access profile lacks 'site_settings' is denied."""
    response = await client.get("/settings", headers=mgmt_auth_headers)
    assert response.status_code == 403


async def test_list_settings_with_permission_returns_catalog(
    client, db, mgmt_auth_headers, test_manager_profile
):
    """A management caller with 'site_settings' sees the full catalog with default values."""
    await _grant_site_settings(db, test_manager_profile)
    await db.commit()

    response = await client.get("/settings", headers=mgmt_auth_headers)

    assert response.status_code == 200
    body = response.json()
    keys = {s["key"] for s in body}
    assert "cash_in_mode" in keys
    assert "hide_variance_on_close" in keys
    cash_in = next(s for s in body if s["key"] == "cash_in_mode")
    assert cash_in["effective_value"] == "bulk"
    assert cash_in["brand_value"] is None
    hide_variance = next(s for s in body if s["key"] == "hide_variance_on_close")
    assert hide_variance["effective_value"] is False


async def test_list_settings_search_filters_by_label(client, db, mgmt_auth_headers, test_manager_profile):
    """The search query param filters the catalog by key/label/category."""
    await _grant_site_settings(db, test_manager_profile)
    await db.commit()

    response = await client.get("/settings", params={"search": "variance"}, headers=mgmt_auth_headers)

    assert response.status_code == 200
    keys = {s["key"] for s in response.json()}
    assert keys == {"hide_variance_on_close"}


async def test_list_settings_requires_authentication(client):
    """No token returns 403."""
    response = await client.get("/settings")
    assert response.status_code == 403


# ── PUT /settings/{key} ────────────────────────────────────────────────────


async def test_update_brand_setting_succeeds(client, db, mgmt_auth_headers, test_manager_profile):
    """Setting a brand-level override (no site_id) updates the brand default."""
    await _grant_site_settings(db, test_manager_profile)
    await db.commit()

    response = await client.put(
        "/settings/hide_variance_on_close", json={"value": True}, headers=mgmt_auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["brand_value"] is True
    assert body["effective_value"] is True


async def test_update_site_setting_succeeds(
    client, db, mgmt_auth_headers, test_manager_profile, test_site
):
    """Setting a site-level override wins over the (unset) brand default."""
    await _grant_site_settings(db, test_manager_profile)
    await db.commit()

    response = await client.put(
        "/settings/cash_in_mode",
        json={"value": "denomination", "site_id": str(test_site.id)},
        headers=mgmt_auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["site_value"] == "denomination"
    assert body["effective_value"] == "denomination"


async def test_update_setting_invalid_option_returns_422(client, db, mgmt_auth_headers, test_manager_profile):
    """A single_select value outside its catalog options is rejected."""
    await _grant_site_settings(db, test_manager_profile)
    await db.commit()

    response = await client.put(
        "/settings/cash_in_mode", json={"value": "not_a_real_mode"}, headers=mgmt_auth_headers
    )

    assert response.status_code == 422


async def test_update_setting_wrong_type_returns_422(client, db, mgmt_auth_headers, test_manager_profile):
    """A non-boolean value for a boolean setting is rejected."""
    await _grant_site_settings(db, test_manager_profile)
    await db.commit()

    response = await client.put(
        "/settings/hide_variance_on_close", json={"value": "yes"}, headers=mgmt_auth_headers
    )

    assert response.status_code == 422


async def test_update_unknown_setting_key_returns_404(client, db, mgmt_auth_headers, test_manager_profile):
    """An unrecognised setting key returns 404."""
    await _grant_site_settings(db, test_manager_profile)
    await db.commit()

    response = await client.put(
        "/settings/not_a_real_setting", json={"value": True}, headers=mgmt_auth_headers
    )

    assert response.status_code == 404


async def test_update_setting_without_permission_returns_403(client, mgmt_auth_headers):
    """A management caller lacking 'site_settings' cannot write."""
    response = await client.put(
        "/settings/hide_variance_on_close", json={"value": True}, headers=mgmt_auth_headers
    )
    assert response.status_code == 403


async def test_update_setting_pos_access_forbidden(client, pos_auth_headers):
    """A raw POS terminal session can never write a setting."""
    response = await client.put(
        "/settings/hide_variance_on_close", json={"value": True}, headers=pos_auth_headers
    )
    assert response.status_code == 403


async def test_update_setting_portal_admin_requires_brand_id(client, portal_auth_headers):
    """A portal admin with no brand_id query param is rejected (brand_id required off-token)."""
    response = await client.put(
        "/settings/hide_variance_on_close", json={"value": True}, headers=portal_auth_headers
    )
    assert response.status_code == 422


async def test_update_setting_writes_audit_log(client, db, mgmt_auth_headers, test_manager_profile, test_brand):
    """Updating a setting writes a SETTING_UPDATED audit row."""
    await _grant_site_settings(db, test_manager_profile)
    await db.commit()

    await client.put("/settings/hide_variance_on_close", json={"value": True}, headers=mgmt_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == "hide_variance_on_close",
            AuditLog.action == SETTING_UPDATED,
        )
    )
    row = result.scalar_one()
    assert row.actor_email == "posuser@test.com"
    assert row.after_state["value"] is True


# ── DELETE /settings/{key} ──────────────────────────────────────────────────


async def test_reset_setting_reverts_to_default(client, db, mgmt_auth_headers, test_manager_profile):
    """Clearing a brand override reverts effective_value to the catalog default."""
    await _grant_site_settings(db, test_manager_profile)
    await db.commit()

    await client.put("/settings/hide_variance_on_close", json={"value": True}, headers=mgmt_auth_headers)
    response = await client.delete("/settings/hide_variance_on_close", headers=mgmt_auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["brand_value"] is None
    assert body["effective_value"] is False


async def test_reset_setting_with_no_override_returns_404(client, db, mgmt_auth_headers, test_manager_profile):
    """Clearing a setting with no existing override returns 404."""
    await _grant_site_settings(db, test_manager_profile)
    await db.commit()

    response = await client.delete("/settings/hide_variance_on_close", headers=mgmt_auth_headers)
    assert response.status_code == 404


async def test_reset_setting_writes_audit_log(client, db, mgmt_auth_headers, test_manager_profile):
    """Resetting a setting writes a SETTING_RESET audit row."""
    await _grant_site_settings(db, test_manager_profile)
    await db.commit()

    await client.put("/settings/hide_variance_on_close", json={"value": True}, headers=mgmt_auth_headers)
    await client.delete("/settings/hide_variance_on_close", headers=mgmt_auth_headers)

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == "hide_variance_on_close",
            AuditLog.action == SETTING_RESET,
        )
    )
    row = result.scalar_one()
    assert row.actor_email == "posuser@test.com"


# ── GET /pos/settings ────────────────────────────────────────────────────────


async def test_pos_settings_returns_effective_values(client, pos_auth_headers):
    """The POS terminal read endpoint resolves the catalog for its own site."""
    response = await client.get("/pos/settings", headers=pos_auth_headers)

    assert response.status_code == 200
    keys = {s["key"] for s in response.json()}
    assert "cash_in_mode" in keys


async def test_pos_settings_reflects_site_override(
    client, db, mgmt_auth_headers, test_manager_profile, test_site, pos_auth_headers
):
    """A site-level override set via the management route is visible to the POS terminal."""
    await _grant_site_settings(db, test_manager_profile)
    await db.commit()

    await client.put(
        "/settings/cash_in_mode",
        json={"value": "denomination", "site_id": str(test_site.id)},
        headers=mgmt_auth_headers,
    )

    response = await client.get("/pos/settings", headers=pos_auth_headers)

    assert response.status_code == 200
    cash_in = next(s for s in response.json() if s["key"] == "cash_in_mode")
    assert cash_in["effective_value"] == "denomination"


async def test_pos_settings_requires_authentication(client):
    """No token returns 403."""
    response = await client.get("/pos/settings")
    assert response.status_code == 403
