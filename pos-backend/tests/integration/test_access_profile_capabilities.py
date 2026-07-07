"""Integration tests for the Stage 24 open-item capability flags on AccessProfile.

Covers:
1. Happy path — set can_use_open_item and open_item_max_price_cents, partial update
2. POS JWT rejected — 403
3. Unknown profile — 404
4. Invalid input — negative price ceiling returns 422
5. Audit log — ACCESS_PROFILE_CAPABILITIES_UPDATED written
"""

import pytest
from sqlalchemy import select

from app.constants.audit_actions import ACCESS_PROFILE_CAPABILITIES_UPDATED
from app.models.audit_log import AuditLog

pytestmark = pytest.mark.asyncio


async def test_update_capabilities_returns_200(
    client, mgmt_auth_headers, test_manager_profile
):
    """PATCH /access-profiles/{id}/capabilities sets both fields."""
    response = await client.patch(
        f"/access-profiles/{test_manager_profile.id}/capabilities",
        json={"can_use_open_item": True, "open_item_max_price_cents": 5000},
        headers=mgmt_auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["can_use_open_item"] is True
    assert body["open_item_max_price_cents"] == 5000


async def test_update_capabilities_partial_update_leaves_other_field(
    client, mgmt_auth_headers, test_manager_profile
):
    """Supplying only one field leaves the other untouched."""
    await client.patch(
        f"/access-profiles/{test_manager_profile.id}/capabilities",
        json={"can_use_open_item": True, "open_item_max_price_cents": 5000},
        headers=mgmt_auth_headers,
    )

    response = await client.patch(
        f"/access-profiles/{test_manager_profile.id}/capabilities",
        json={"can_use_open_item": False},
        headers=mgmt_auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["can_use_open_item"] is False
    assert body["open_item_max_price_cents"] == 5000


async def test_update_capabilities_writes_audit_log(
    client, db, mgmt_auth_headers, test_manager_profile, test_user
):
    """Updating capabilities writes an ACCESS_PROFILE_CAPABILITIES_UPDATED audit row."""
    await client.patch(
        f"/access-profiles/{test_manager_profile.id}/capabilities",
        json={"can_use_open_item": True},
        headers=mgmt_auth_headers,
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.action == ACCESS_PROFILE_CAPABILITIES_UPDATED,
            AuditLog.entity_id == str(test_manager_profile.id),
        )
    )
    row = result.scalar_one()
    assert row.actor_id == test_user.id


async def test_update_capabilities_pos_token_returns_403(client, pos_auth_headers, test_access_profile):
    """A POS JWT cannot manage access profile capabilities."""
    response = await client.patch(
        f"/access-profiles/{test_access_profile.id}/capabilities",
        json={"can_use_open_item": True},
        headers=pos_auth_headers,
    )
    assert response.status_code == 403


async def test_update_capabilities_unknown_profile_returns_404(client, mgmt_auth_headers):
    """An unknown access_profile_id returns 404."""
    import uuid

    response = await client.patch(
        f"/access-profiles/{uuid.uuid4()}/capabilities",
        json={"can_use_open_item": True},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 404


async def test_update_capabilities_negative_price_returns_422(
    client, mgmt_auth_headers, test_manager_profile
):
    """A negative open_item_max_price_cents returns 422."""
    response = await client.patch(
        f"/access-profiles/{test_manager_profile.id}/capabilities",
        json={"open_item_max_price_cents": -1},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 422
