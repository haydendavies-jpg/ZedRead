"""Integration tests for site product override routes and the resolved catalog.

Covers:
1. Happy path — set override, resolved catalog applies price override
2. Exclusion — excluded product absent from resolved catalog
3. No override — base price used when no override row exists
4. Business rules — 404 for unknown site/product; 404 on remove non-existent
5. Audit log — SITE_PRODUCT_OVERRIDE_SET and REMOVED written correctly
"""

import pytest
from sqlalchemy import select

from app.constants.audit_actions import SITE_PRODUCT_OVERRIDE_REMOVED, SITE_PRODUCT_OVERRIDE_SET
from app.models.audit_log import AuditLog

pytestmark = pytest.mark.asyncio


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_set_override_returns_200(client, pos_auth_headers, test_product, test_site):
    """PUT /site-overrides/{site_id}/{product_id} creates an override and returns 200."""
    response = await client.put(
        f"/site-overrides/{test_site.id}/{test_product.id}",
        json={"override_price_cents": 999, "is_excluded": False},
        headers=pos_auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["override_price_cents"] == 999
    assert body["is_excluded"] is False
    assert body["site_id"] == str(test_site.id)
    assert body["product_id"] == str(test_product.id)


async def test_set_override_is_idempotent(client, pos_auth_headers, test_product, test_site):
    """Calling PUT twice updates the existing override row — no duplicates."""
    await client.put(
        f"/site-overrides/{test_site.id}/{test_product.id}",
        json={"override_price_cents": 999, "is_excluded": False},
        headers=pos_auth_headers,
    )
    response = await client.put(
        f"/site-overrides/{test_site.id}/{test_product.id}",
        json={"override_price_cents": 1100, "is_excluded": False},
        headers=pos_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["override_price_cents"] == 1100


async def test_set_override_writes_audit_log(
    client, db, pos_auth_headers, test_product, test_site, test_pos_user
):
    """Setting an override writes a SITE_PRODUCT_OVERRIDE_SET audit row."""
    await client.put(
        f"/site-overrides/{test_site.id}/{test_product.id}",
        json={"override_price_cents": 999, "is_excluded": False},
        headers=pos_auth_headers,
    )

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == SITE_PRODUCT_OVERRIDE_SET)
    )
    row = result.scalar_one()
    assert row.actor_id == test_pos_user.id


# ── Resolved catalog ─────────────────────────────────────────────────────────


async def test_resolved_catalog_applies_price_override(
    client, pos_auth_headers, test_product, test_site
):
    """GET /site-overrides/{site_id}/catalog applies override_price_cents."""
    await client.put(
        f"/site-overrides/{test_site.id}/{test_product.id}",
        json={"override_price_cents": 888, "is_excluded": False},
        headers=pos_auth_headers,
    )

    response = await client.get(
        f"/site-overrides/{test_site.id}/catalog",
        headers=pos_auth_headers,
    )

    assert response.status_code == 200
    products = response.json()
    match = next((p for p in products if p["product_id"] == str(test_product.id)), None)
    assert match is not None
    assert match["effective_price_cents"] == 888


async def test_resolved_catalog_uses_base_price_when_no_override(
    client, pos_auth_headers, test_product, test_site
):
    """Resolved catalog uses base_price_cents when no override row exists."""
    response = await client.get(
        f"/site-overrides/{test_site.id}/catalog",
        headers=pos_auth_headers,
    )

    assert response.status_code == 200
    products = response.json()
    match = next((p for p in products if p["product_id"] == str(test_product.id)), None)
    assert match is not None
    assert match["effective_price_cents"] == test_product.base_price_cents


async def test_resolved_catalog_excludes_excluded_product(
    client, pos_auth_headers, test_product, test_site
):
    """Products with is_excluded=True do not appear in the resolved catalog."""
    await client.put(
        f"/site-overrides/{test_site.id}/{test_product.id}",
        json={"override_price_cents": None, "is_excluded": True},
        headers=pos_auth_headers,
    )

    response = await client.get(
        f"/site-overrides/{test_site.id}/catalog",
        headers=pos_auth_headers,
    )

    assert response.status_code == 200
    product_ids = [p["product_id"] for p in response.json()]
    assert str(test_product.id) not in product_ids


# ── Remove override ───────────────────────────────────────────────────────────


async def test_remove_override_returns_204(client, pos_auth_headers, test_product, test_site):
    """DELETE /site-overrides/{site_id}/{product_id} removes the override and returns 204."""
    await client.put(
        f"/site-overrides/{test_site.id}/{test_product.id}",
        json={"override_price_cents": 999, "is_excluded": False},
        headers=pos_auth_headers,
    )

    response = await client.delete(
        f"/site-overrides/{test_site.id}/{test_product.id}",
        headers=pos_auth_headers,
    )

    assert response.status_code == 204


async def test_remove_override_restores_base_price(
    client, pos_auth_headers, test_product, test_site
):
    """After removing an override, the catalog returns the base price."""
    await client.put(
        f"/site-overrides/{test_site.id}/{test_product.id}",
        json={"override_price_cents": 999, "is_excluded": False},
        headers=pos_auth_headers,
    )
    await client.delete(
        f"/site-overrides/{test_site.id}/{test_product.id}",
        headers=pos_auth_headers,
    )

    response = await client.get(
        f"/site-overrides/{test_site.id}/catalog",
        headers=pos_auth_headers,
    )

    products = response.json()
    match = next((p for p in products if p["product_id"] == str(test_product.id)), None)
    assert match is not None
    assert match["effective_price_cents"] == test_product.base_price_cents


async def test_remove_override_writes_audit_log(
    client, db, pos_auth_headers, test_product, test_site, test_pos_user
):
    """Removing an override writes a SITE_PRODUCT_OVERRIDE_REMOVED audit row."""
    await client.put(
        f"/site-overrides/{test_site.id}/{test_product.id}",
        json={"override_price_cents": 999, "is_excluded": False},
        headers=pos_auth_headers,
    )
    await client.delete(
        f"/site-overrides/{test_site.id}/{test_product.id}",
        headers=pos_auth_headers,
    )

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == SITE_PRODUCT_OVERRIDE_REMOVED)
    )
    row = result.scalar_one()
    assert row.actor_id == test_pos_user.id


async def test_remove_nonexistent_override_returns_404(
    client, pos_auth_headers, test_product, test_site
):
    """Removing an override that doesn't exist returns 404."""
    response = await client.delete(
        f"/site-overrides/{test_site.id}/{test_product.id}",
        headers=pos_auth_headers,
    )

    assert response.status_code == 404
