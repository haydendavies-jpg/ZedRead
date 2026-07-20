"""Integration tests for the POS User password-reset email flow.

Covers:
1. Happy path — portal admin/management trigger sends a reset email and sets
   a token; the emailed token resets the password via the existing
   /auth/portal/reset-password endpoint (shared with portal-admin resets).
2. Auth failure — POS terminal JWT cannot trigger a reset.
3. Business rules — user has no email (409), management caller outside
   scope (403), unknown user (404).
4. Audit log — AUTH_PASSWORD_RESET_REQUESTED written on trigger.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.constants.audit_actions import AUTH_PASSWORD_RESET_REQUESTED
from app.models.audit_log import AuditLog
from app.models.brand import Brand
from app.models.group import Group
from app.models.user import User
from app.utils.security import create_access_token, create_mgmt_access_token, hash_password

pytestmark = pytest.mark.asyncio

_SEND_RESET_EMAIL_PATH = "app.services.user_service.send_password_reset_email"


def _portal_headers(superadmin) -> dict[str, str]:
    """Return portal JWT headers."""
    token = create_access_token(str(superadmin.id), superadmin.superadmin_role)
    return {"Authorization": f"Bearer {token}"}


def _mgmt_headers(user, grant) -> dict[str, str]:
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


# ── Happy path ───────────────────────────────────────────────────────────────


async def test_send_password_reset_superadmin_sends_email_and_sets_token(
    client, db, test_superadmin, test_user
):
    """A portal admin can trigger a reset email for any User; a token is generated."""
    with patch(_SEND_RESET_EMAIL_PATH, new_callable=AsyncMock) as mock_send:
        response = await client.post(
            f"/users/{test_user.id}/send-password-reset", headers=_portal_headers(test_superadmin)
        )

    assert response.status_code == 204
    assert mock_send.called

    await db.refresh(test_user)
    assert test_user.password_reset_token is not None
    assert test_user.password_reset_token_expires_at is not None


async def test_send_password_reset_writes_audit_log(client, db, test_superadmin, test_user):
    """Triggering a reset writes an AUTH_PASSWORD_RESET_REQUESTED row for the target user."""
    with patch(_SEND_RESET_EMAIL_PATH, new_callable=AsyncMock):
        await client.post(
            f"/users/{test_user.id}/send-password-reset", headers=_portal_headers(test_superadmin)
        )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_user.id),
            AuditLog.action == AUTH_PASSWORD_RESET_REQUESTED,
        )
    )
    row = result.scalar_one()
    assert row.actor_id == test_superadmin.id


async def test_reset_password_consumes_user_token_and_changes_password(
    client, db, test_superadmin, test_user, test_site, test_access_grant, test_device
):
    """The emailed token resets the User's password via /auth/portal/reset-password,
    and the new password can then be used to log into the POS terminal."""
    with patch(_SEND_RESET_EMAIL_PATH, new_callable=AsyncMock):
        await client.post(
            f"/users/{test_user.id}/send-password-reset", headers=_portal_headers(test_superadmin)
        )

    await db.refresh(test_user)
    token = test_user.password_reset_token

    reset_resp = await client.post(
        "/auth/portal/reset-password",
        json={"token": token, "new_password": "BrandNewUserPassword123!"},
    )
    assert reset_resp.status_code == 204

    login_resp = await client.post(
        "/auth/pos/login",
        json={
            "email": "posuser@test.com",
            "password": "BrandNewUserPassword123!",
            "device_token": test_device.device_token,
        },
    )
    assert login_resp.status_code == 200


async def test_reset_password_token_single_use_across_user_and_superadmin_tables(
    client, db, test_superadmin, test_user
):
    """A consumed User reset token cannot be replayed."""
    with patch(_SEND_RESET_EMAIL_PATH, new_callable=AsyncMock):
        await client.post(
            f"/users/{test_user.id}/send-password-reset", headers=_portal_headers(test_superadmin)
        )
    await db.refresh(test_user)
    token = test_user.password_reset_token

    first = await client.post(
        "/auth/portal/reset-password", json={"token": token, "new_password": "FirstPassword123!"}
    )
    assert first.status_code == 204

    second = await client.post(
        "/auth/portal/reset-password", json={"token": token, "new_password": "SecondPassword123!"}
    )
    assert second.status_code == 400


# ── Business rules ─────────────────────────────────────────────────────────────


async def test_send_password_reset_no_email_returns_409(client, db, test_superadmin, test_brand):
    """A User with no email on file cannot have a reset triggered."""
    passwordless_user = User(
        id=uuid.uuid4(),
        group_id=test_brand.group_id,
        brand_id=test_brand.id,
        name="No Email User",
        first_name="No",
        last_name="Email",
        is_active=True,
    )
    db.add(passwordless_user)
    await db.commit()

    response = await client.post(
        f"/users/{passwordless_user.id}/send-password-reset", headers=_portal_headers(test_superadmin)
    )
    assert response.status_code == 409


async def test_send_password_reset_unknown_user_returns_404(client, test_superadmin):
    """An unknown user id returns 404."""
    response = await client.post(
        f"/users/{uuid.uuid4()}/send-password-reset", headers=_portal_headers(test_superadmin)
    )
    assert response.status_code == 404


async def test_send_password_reset_mgmt_caller_outside_scope_returns_403(
    client, db, test_user, test_brand_grant, test_group
):
    """A brand-scope management caller cannot trigger a reset for a user in another brand."""
    other_brand = Brand(
        id=uuid.uuid4(),
        group_id=test_group.id,
        name="Other Brand",
        is_active=True,
        timezone="Australia/Sydney",
        currency="AUD",
        country="AU",
    )
    db.add(other_brand)
    await db.commit()

    other_user = User(
        id=uuid.uuid4(),
        group_id=other_brand.group_id,
        brand_id=other_brand.id,
        name="Other Brand User",
        email="otherbranduser@test.com",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    db.add(other_user)
    await db.commit()

    response = await client.post(
        f"/users/{other_user.id}/send-password-reset", headers=_mgmt_headers(test_user, test_brand_grant)
    )
    assert response.status_code == 403


async def test_send_password_reset_mgmt_caller_in_scope_succeeds(
    client, db, test_user, test_brand, test_brand_grant
):
    """A brand-scope management caller can trigger a reset for a colleague in the same brand."""
    colleague = User(
        id=uuid.uuid4(),
        group_id=test_brand.group_id,
        brand_id=test_brand.id,
        name="Colleague",
        email="colleague@test.com",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    db.add(colleague)
    await db.commit()

    with patch(_SEND_RESET_EMAIL_PATH, new_callable=AsyncMock) as mock_send:
        response = await client.post(
            f"/users/{colleague.id}/send-password-reset", headers=_mgmt_headers(test_user, test_brand_grant)
        )
    assert response.status_code == 204
    assert mock_send.called


async def test_send_password_reset_pos_jwt_forbidden(client, pos_auth_headers, test_user):
    """A POS terminal JWT cannot trigger a password reset."""
    response = await client.post(f"/users/{test_user.id}/send-password-reset", headers=pos_auth_headers)
    assert response.status_code == 403
