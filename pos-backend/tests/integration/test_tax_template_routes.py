"""Integration tests for admin tax templates and site-level tax resolution.

Covers:
1. POST /admin/tax-templates creates a template (audit logged) and requires an admin token.
2. Rates are added, updated, soft-deleted (audit logged) and returned nested in the template.
3. The jurisdiction matching rule: a template applies when every set field matches the
   site's location; unset template fields are ignored; a set field the site lacks excludes it.
4. Brand creation seeds the Standard / Tax Free system taxability categories.
5. tax_resolution_service resolves and combines the right rates for a site.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.constants.audit_actions import TAX_TEMPLATE_CREATED, TAX_TEMPLATE_RATE_CREATED
from app.models.audit_log import AuditLog
from app.models.tax_category import TaxCategory
from app.services.tax_resolution_service import resolve_rates_for_location, resolve_rates_for_site


# ── Admin routes: auth + CRUD + audit ────────────────────────────────────────


async def test_create_tax_template_requires_admin(client):
    """POST /admin/tax-templates without a token is rejected."""
    resp = await client.post("/admin/tax-templates/", json={"name": "AU", "country": "AU"})
    assert resp.status_code in (401, 403)


async def test_create_tax_template_returns_201_and_audits(client, db, portal_auth_headers, test_superadmin):
    """Creating a template returns 201 and writes a TAX_TEMPLATE_CREATED audit row."""
    resp = await client.post(
        "/admin/tax-templates/",
        json={"name": "Australia GST", "country": "au"},
        headers=portal_auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["country"] == "AU"  # normalised to upper-case
    assert body["rates"] == []

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == body["id"],
            AuditLog.action == TAX_TEMPLATE_CREATED,
        )
    )
    row = result.scalar_one()
    assert row.actor_id == test_superadmin.id


async def test_add_rate_returns_201_and_audits(client, db, portal_auth_headers):
    """Adding a rate to a template returns 201, audits, and appears nested on the template."""
    t = await client.post(
        "/admin/tax-templates/",
        json={"name": "Australia GST", "country": "AU"},
        headers=portal_auth_headers,
    )
    template_id = t.json()["id"]

    r = await client.post(
        f"/admin/tax-templates/{template_id}/rates",
        json={"name": "GST", "rate_percent": "10.0000", "tax_model": "inclusive"},
        headers=portal_auth_headers,
    )
    assert r.status_code == 201, r.text
    rate_id = r.json()["id"]

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == rate_id,
            AuditLog.action == TAX_TEMPLATE_RATE_CREATED,
        )
    )
    assert result.scalar_one() is not None

    listed = await client.get("/admin/tax-templates/", headers=portal_auth_headers)
    template = next(t for t in listed.json() if t["id"] == template_id)
    assert len(template["rates"]) == 1
    assert template["rates"][0]["name"] == "GST"


async def test_delete_rate_soft_deletes(client, db, portal_auth_headers):
    """A deleted rate no longer appears on the template."""
    t = await client.post(
        "/admin/tax-templates/",
        json={"name": "Australia GST", "country": "AU"},
        headers=portal_auth_headers,
    )
    template_id = t.json()["id"]
    r = await client.post(
        f"/admin/tax-templates/{template_id}/rates",
        json={"name": "GST", "rate_percent": "10", "tax_model": "inclusive"},
        headers=portal_auth_headers,
    )
    rate_id = r.json()["id"]

    d = await client.delete(f"/admin/tax-templates/rates/{rate_id}", headers=portal_auth_headers)
    assert d.status_code == 200

    listed = await client.get("/admin/tax-templates/", headers=portal_auth_headers)
    template = next(t for t in listed.json() if t["id"] == template_id)
    assert template["rates"] == []


# ── Brand seeding ────────────────────────────────────────────────────────────


async def test_brand_creation_seeds_system_tax_categories(client, db, portal_auth_headers):
    """POST /brands/ seeds a Standard (taxed) and a Tax Free system category."""
    g = await client.post(
        "/groups/",
        json={"name": "Seed Grp", "master_email": "seedgrp@example.com", "master_password": "SecurePass1!"},
        headers=portal_auth_headers,
    )
    group_id = g.json()["id"]
    b = await client.post(
        "/brands/",
        json={"group_id": group_id, "name": "Seed Brand", "master_email": "seedbrand@example.com", "master_password": "SecurePass1!"},
        headers=portal_auth_headers,
    )
    assert b.status_code == 201, b.text
    brand_id = uuid.UUID(b.json()["id"])

    result = await db.execute(
        select(TaxCategory).where(TaxCategory.brand_id == brand_id, TaxCategory.is_system == True)  # noqa: E712
    )
    cats = {c.name: c for c in result.scalars().all()}
    assert "Standard" in cats and cats["Standard"].is_tax_free is False
    assert "Tax Free" in cats and cats["Tax Free"].is_tax_free is True


# ── Resolution / matching logic ──────────────────────────────────────────────


async def test_resolution_ignores_unset_template_fields(client, db, portal_auth_headers):
    """A country-only AU template applies to an AU site regardless of state/city."""
    t = await client.post(
        "/admin/tax-templates/",
        json={"name": "Australia GST", "country": "AU"},
        headers=portal_auth_headers,
    )
    template_id = t.json()["id"]
    await client.post(
        f"/admin/tax-templates/{template_id}/rates",
        json={"name": "GST", "rate_percent": "10", "tax_model": "inclusive"},
        headers=portal_auth_headers,
    )

    rates = await resolve_rates_for_location(db, country="AU", state="NSW", city="Sydney")
    assert len(rates) == 1
    assert rates[0]["rate_name"] == "GST"
    assert rates[0]["rate_percent"] == Decimal("10.0000")


async def test_resolution_excludes_state_template_for_other_state(client, db, portal_auth_headers):
    """A template scoped to state=TX must not apply to a NSW location."""
    t = await client.post(
        "/admin/tax-templates/",
        json={"name": "Texas", "country": "US", "state": "TX"},
        headers=portal_auth_headers,
    )
    await client.post(
        f"/admin/tax-templates/{t.json()['id']}/rates",
        json={"name": "TX Sales", "rate_percent": "6.25", "tax_model": "exclusive"},
        headers=portal_auth_headers,
    )
    # A US site in a different state gets no rates from the TX-scoped template
    rates = await resolve_rates_for_location(db, country="US", state="CA")
    assert rates == []


async def test_resolution_combines_country_and_state_templates(client, db, portal_auth_headers):
    """A US country template and a US/TX template both apply to a Texan site — rates combine."""
    country_t = await client.post(
        "/admin/tax-templates/",
        json={"name": "US Federal", "country": "US"},
        headers=portal_auth_headers,
    )
    await client.post(
        f"/admin/tax-templates/{country_t.json()['id']}/rates",
        json={"name": "Federal", "rate_percent": "2", "tax_model": "exclusive"},
        headers=portal_auth_headers,
    )
    state_t = await client.post(
        "/admin/tax-templates/",
        json={"name": "Texas", "country": "US", "state": "TX"},
        headers=portal_auth_headers,
    )
    await client.post(
        f"/admin/tax-templates/{state_t.json()['id']}/rates",
        json={"name": "TX Sales", "rate_percent": "6.25", "tax_model": "exclusive"},
        headers=portal_auth_headers,
    )

    rates = await resolve_rates_for_location(db, country="US", state="TX")
    names = {r["rate_name"] for r in rates}
    assert names == {"Federal", "TX Sales"}


async def test_resolve_rates_for_site_uses_site_location(client, db, portal_auth_headers, test_site):
    """resolve_rates_for_site derives AU from the test site (country=AU)."""
    t = await client.post(
        "/admin/tax-templates/",
        json={"name": "Australia GST", "country": "AU"},
        headers=portal_auth_headers,
    )
    await client.post(
        f"/admin/tax-templates/{t.json()['id']}/rates",
        json={"name": "GST", "rate_percent": "10", "tax_model": "inclusive"},
        headers=portal_auth_headers,
    )

    rates = await resolve_rates_for_site(db, test_site.id)
    assert len(rates) == 1
    assert rates[0]["rate_name"] == "GST"
