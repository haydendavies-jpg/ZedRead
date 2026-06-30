"""Integration tests for /email-templates routes.

Covers all five required scenarios per tests_CLAUDE.md:
1. Happy path — list/get/create/update return correct shapes
2. Auth failure — no token → 403, non-Admin SuperAdmin → 403
3. Invalid input — missing fields → 422
4. Business rule — 404 for unknown template, 409 for duplicate template_key
5. Audit log — every write asserts the correct audit_logs row
"""

import uuid

from sqlalchemy import select

from app.constants.audit_actions import EMAIL_TEMPLATE_CREATED, EMAIL_TEMPLATE_UPDATED
from app.models.audit_log import AuditLog
from app.utils.security import hash_password

_CREATE_PAYLOAD = {
    "template_key": "test_template",
    "name": "Test Template",
    "subject": "Hello $entity_name",
    "body": "Body for $entity_type $entity_name.",
}


async def _reseller_staff_headers(db) -> dict[str, str]:
    """Create a Reseller Staff SuperAdmin and return a valid Authorization header for them."""
    from app.models.superadmin import SuperAdmin
    from app.utils.security import create_access_token

    user = SuperAdmin(
        id=uuid.uuid4(),
        email="reseller@test.com",
        password_hash=hash_password("TestPassword123!"),
        name="Reseller Staff",
        role="reseller_staff",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(str(user.id), user.role)
    return {"Authorization": f"Bearer {token}"}


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_create_email_template_returns_201(client, portal_auth_headers):
    """POST /email-templates creates a template and returns 201 with the correct shape."""
    response = await client.post(
        "/email-templates/", json=_CREATE_PAYLOAD, headers=portal_auth_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["template_key"] == "test_template"
    assert body["name"] == "Test Template"
    assert body["is_system"] is False
    assert body["is_active"] is True


async def test_list_email_templates_returns_200(client, portal_auth_headers, test_billing_info_template):
    """GET /email-templates returns 200 with a list containing the seeded template."""
    response = await client.get("/email-templates/", headers=portal_auth_headers)

    assert response.status_code == 200
    keys = [t["template_key"] for t in response.json()]
    assert "billing_info_request" in keys


async def test_get_email_template_returns_correct_template(
    client, portal_auth_headers, test_billing_info_template
):
    """GET /email-templates/{id} returns the correct template."""
    response = await client.get(
        f"/email-templates/{test_billing_info_template.id}", headers=portal_auth_headers
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(test_billing_info_template.id)


async def test_update_email_template(client, portal_auth_headers, test_billing_info_template):
    """PATCH /email-templates/{id} updates mutable fields and returns the updated template."""
    response = await client.patch(
        f"/email-templates/{test_billing_info_template.id}",
        json={"subject": "Updated subject for $entity_name"},
        headers=portal_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["subject"] == "Updated subject for $entity_name"


# ── Auth failure ──────────────────────────────────────────────────────────────


async def test_list_email_templates_no_token_returns_403(client):
    """GET /email-templates without a token returns 403."""
    response = await client.get("/email-templates/")
    assert response.status_code == 403


async def test_create_email_template_no_token_returns_403(client):
    """POST /email-templates without a token returns 403."""
    response = await client.post("/email-templates/", json=_CREATE_PAYLOAD)
    assert response.status_code == 403


async def test_create_email_template_non_admin_returns_403(client, db):
    """POST /email-templates as a Reseller Staff (non-Admin) SuperAdmin returns 403."""
    headers = await _reseller_staff_headers(db)
    response = await client.post("/email-templates/", json=_CREATE_PAYLOAD, headers=headers)
    assert response.status_code == 403


# ── Invalid input ─────────────────────────────────────────────────────────────


async def test_create_email_template_missing_fields_returns_422(client, portal_auth_headers):
    """POST /email-templates with no body returns 422."""
    response = await client.post(
        "/email-templates/", json={"template_key": "incomplete"}, headers=portal_auth_headers
    )
    assert response.status_code == 422


# ── Business rule violations ──────────────────────────────────────────────────


async def test_get_unknown_email_template_returns_404(client, portal_auth_headers):
    """GET /email-templates/{unknown_id} returns 404."""
    response = await client.get(f"/email-templates/{uuid.uuid4()}", headers=portal_auth_headers)
    assert response.status_code == 404


async def test_create_email_template_duplicate_key_returns_409(client, portal_auth_headers):
    """POST /email-templates with an already-used template_key returns 409."""
    await client.post("/email-templates/", json=_CREATE_PAYLOAD, headers=portal_auth_headers)
    response = await client.post(
        "/email-templates/", json=_CREATE_PAYLOAD, headers=portal_auth_headers
    )
    assert response.status_code == 409


# ── Audit log assertions ──────────────────────────────────────────────────────


async def test_create_email_template_writes_audit_log(client, db, portal_auth_headers):
    """POST /email-templates writes an EMAIL_TEMPLATE_CREATED audit row."""
    response = await client.post(
        "/email-templates/", json=_CREATE_PAYLOAD, headers=portal_auth_headers
    )
    template_id = response.json()["id"]

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == template_id,
            AuditLog.action == EMAIL_TEMPLATE_CREATED,
        )
    )
    row = result.scalar_one()
    assert row.after_state["template_key"] == "test_template"


async def test_update_email_template_writes_audit_log(
    client, db, portal_auth_headers, test_billing_info_template
):
    """PATCH /email-templates/{id} writes an EMAIL_TEMPLATE_UPDATED audit row with before/after."""
    await client.patch(
        f"/email-templates/{test_billing_info_template.id}",
        json={"name": "Renamed Template"},
        headers=portal_auth_headers,
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(test_billing_info_template.id),
            AuditLog.action == EMAIL_TEMPLATE_UPDATED,
        )
    )
    row = result.scalar_one()
    assert row.before_state["name"] == "Billing Info Request"
    assert row.after_state["name"] == "Renamed Template"
