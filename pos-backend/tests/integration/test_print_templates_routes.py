"""Integration tests for /print-templates routes and the GET /pos/print-config contract.

Covers:
1. Happy path — brand creation seeds the 3 singleton templates; list/get/rename/replace-elements;
   GET /pos/print-config returns locations + templates + company profile
2. Auth failure — no token → 401; POS token returns 403 on writes
3. Invalid input — an out-of-catalog field_key on PUT .../elements returns 422
4. Business rules — n/a beyond field_key/section validation
5. Audit log — PRINT_TEMPLATE_UPDATED, PRINT_TEMPLATE_ELEMENTS_UPDATED
"""

import uuid

import pytest
from sqlalchemy import select

from app.constants.audit_actions import PRINT_TEMPLATE_ELEMENTS_UPDATED, PRINT_TEMPLATE_UPDATED
from app.models.audit_log import AuditLog

pytestmark = pytest.mark.asyncio

_MASTER_CREDS = {"master_email": "owner@printtest.example", "master_password": "TestPass123!"}


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_create_brand_seeds_three_singleton_templates(client, portal_auth_headers, test_group):
    """Creating a brand auto-seeds invoice/register_summary/cash_in_slip print templates."""
    response = await client.post(
        "/brands/",
        json={"group_id": str(test_group.id), "name": "Print Test Brand", **_MASTER_CREDS},
        headers=portal_auth_headers,
    )
    brand_id = response.json()["id"]

    mgmt_resp = await client.get("/print-templates", params={"brand_id": brand_id}, headers=portal_auth_headers)
    assert mgmt_resp.status_code == 200
    types = {t["template_type"] for t in mgmt_resp.json()}
    assert types == {"invoice", "register_summary", "cash_in_slip"}


async def test_list_print_templates_filters_by_type(client, mgmt_auth_headers, test_brand):
    """GET /print-templates?template_type=invoice returns only the invoice template."""
    response = await client.get("/print-templates", params={"template_type": "invoice"}, headers=mgmt_auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["template_type"] == "invoice"


async def test_get_print_template_detail_includes_default_elements(client, mgmt_auth_headers, test_brand):
    """GET /print-templates/{id} returns the template's seeded default elements."""
    list_resp = await client.get("/print-templates", params={"template_type": "invoice"}, headers=mgmt_auth_headers)
    template_id = list_resp.json()[0]["id"]

    response = await client.get(f"/print-templates/{template_id}", headers=mgmt_auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body["elements"]) > 0
    assert any(e["field_key"] == "STORE_NAME" for e in body["elements"])


async def test_rename_print_template(client, mgmt_auth_headers, test_brand):
    """PATCH /print-templates/{id} renames the template."""
    list_resp = await client.get("/print-templates", params={"template_type": "invoice"}, headers=mgmt_auth_headers)
    template_id = list_resp.json()[0]["id"]

    response = await client.patch(
        f"/print-templates/{template_id}", json={"name": "Customer Invoice"}, headers=mgmt_auth_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Customer Invoice"


async def test_replace_elements_persists_new_ordered_list(client, mgmt_auth_headers, test_brand):
    """PUT /print-templates/{id}/elements replaces the whole element list."""
    list_resp = await client.get("/print-templates", params={"template_type": "invoice"}, headers=mgmt_auth_headers)
    template_id = list_resp.json()[0]["id"]

    new_elements = [
        {"section": "header", "display_order": 0, "field_key": "STORE_NAME", "alignment": "center", "is_bold": True},
        {"section": "items", "display_order": 0, "field_key": "PRODUCT_LINE", "alignment": "left"},
        {"section": "footer", "display_order": 0, "field_key": "FREE_TEXT", "alignment": "center", "free_text_value": "Thanks!"},
    ]
    response = await client.put(
        f"/print-templates/{template_id}/elements", json={"elements": new_elements}, headers=mgmt_auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["elements"]) == 3
    assert body["elements"][2]["free_text_value"] == "Thanks!"


async def test_pos_print_config_returns_locations_templates_and_company_profile(
    client, db, pos_auth_headers, test_site, mgmt_auth_headers
):
    """GET /pos/print-config returns printer locations, templates with elements, and company profile fields."""
    await client.post("/printer-locations", json={"name": "Kitchen"}, headers=mgmt_auth_headers)

    response = await client.get(
        "/pos/print-config", params={"site_id": str(test_site.id)}, headers=pos_auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert any(loc["name"] == "Kitchen" for loc in body["printer_locations"])
    template_types = {t["template_type"] for t in body["templates"]}
    assert {"invoice", "docket", "register_summary", "cash_in_slip"} <= template_types
    assert body["company_profile"]["store_name"] == test_site.name


# ── Auth failure ──────────────────────────────────────────────────────────────


async def test_rename_print_template_no_token_returns_403(client, test_brand):
    """PATCH /print-templates/{id} with no auth token returns 403."""
    response = await client.patch(f"/print-templates/{uuid.uuid4()}", json={"name": "X"})
    assert response.status_code == 403


async def test_replace_elements_pos_token_returns_403(client, pos_auth_headers, test_brand):
    """PUT /print-templates/{id}/elements with a POS terminal token returns 403."""
    response = await client.put(
        f"/print-templates/{uuid.uuid4()}/elements", json={"elements": []}, headers=pos_auth_headers
    )
    assert response.status_code == 403


# ── Invalid input ─────────────────────────────────────────────────────────────


async def test_replace_elements_invalid_field_key_returns_422(client, mgmt_auth_headers, test_brand):
    """PUT /print-templates/{id}/elements rejects a field_key not valid for the template's type/section."""
    list_resp = await client.get("/print-templates", params={"template_type": "invoice"}, headers=mgmt_auth_headers)
    template_id = list_resp.json()[0]["id"]

    response = await client.put(
        f"/print-templates/{template_id}/elements",
        json={"elements": [{"section": "items", "display_order": 0, "field_key": "CASH_IN_AMOUNT"}]},
        headers=mgmt_auth_headers,
    )
    assert response.status_code == 422


# ── Audit log ─────────────────────────────────────────────────────────────────


async def test_rename_print_template_writes_audit_log(client, db, mgmt_auth_headers, test_brand):
    """Renaming a print template writes a PRINT_TEMPLATE_UPDATED audit row."""
    list_resp = await client.get("/print-templates", params={"template_type": "invoice"}, headers=mgmt_auth_headers)
    template_id = list_resp.json()[0]["id"]

    await client.patch(f"/print-templates/{template_id}", json={"name": "Renamed"}, headers=mgmt_auth_headers)

    audit = await db.execute(
        select(AuditLog).where(AuditLog.entity_id == template_id, AuditLog.action == PRINT_TEMPLATE_UPDATED)
    )
    assert audit.scalar_one() is not None


async def test_replace_elements_writes_audit_log(client, db, mgmt_auth_headers, test_brand):
    """Replacing a template's elements writes a PRINT_TEMPLATE_ELEMENTS_UPDATED audit row."""
    list_resp = await client.get("/print-templates", params={"template_type": "invoice"}, headers=mgmt_auth_headers)
    template_id = list_resp.json()[0]["id"]

    await client.put(
        f"/print-templates/{template_id}/elements",
        json={"elements": [{"section": "header", "display_order": 0, "field_key": "STORE_NAME"}]},
        headers=mgmt_auth_headers,
    )

    audit = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == template_id, AuditLog.action == PRINT_TEMPLATE_ELEMENTS_UPDATED
        )
    )
    assert audit.scalar_one() is not None
