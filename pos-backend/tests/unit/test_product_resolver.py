"""Unit tests for the product resolver.

Covers:
1. Happy path — all products returned with base price when no overrides exist
2. Price override applied — effective_price_cents uses override value
3. Exclusion — is_excluded=True removes product from results
4. Category filter — only products in specified category returned
5. Mixed overrides — some products overridden, some excluded, some at base price
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.category import Category
from app.models.product import Product
from app.models.site_product_override import SiteProductOverride
from app.services.product_resolver import resolve_products_for_site

pytestmark = pytest.mark.asyncio


async def _make_product(db, brand_id: uuid.UUID, category_id: uuid.UUID, name: str, price: int) -> Product:
    """Insert a product and return the persisted instance."""
    p = Product(
        id=uuid.uuid4(),
        brand_id=brand_id,
        category_id=category_id,
        name=name,
        base_price_cents=price,
        display_order=0,
        is_active=True,
    )
    db.add(p)
    await db.flush()
    return p


async def _make_category(db, brand_id: uuid.UUID, name: str = "Test Cat") -> Category:
    """Insert a category and return the persisted instance."""
    cat = Category(
        id=uuid.uuid4(),
        brand_id=brand_id,
        name=name,
        is_system=False,
        is_active=True,
    )
    db.add(cat)
    await db.flush()
    return cat


async def test_resolver_returns_all_active_products_at_base_price(
    db, test_brand, test_site
):
    """All active products returned with base price when no overrides exist."""
    cat = await _make_category(db, test_brand.id)
    p1 = await _make_product(db, test_brand.id, cat.id, "Product A", 1000)
    p2 = await _make_product(db, test_brand.id, cat.id, "Product B", 2000)
    await db.commit()

    results = await resolve_products_for_site(db, test_brand.id, test_site.id)

    result_map = {str(r.product_id): r for r in results}
    assert str(p1.id) in result_map
    assert str(p2.id) in result_map
    assert result_map[str(p1.id)].effective_price_cents == 1000
    assert result_map[str(p2.id)].effective_price_cents == 2000


async def test_resolver_applies_price_override(db, test_brand, test_site):
    """Override price replaces base price for the correct product."""
    cat = await _make_category(db, test_brand.id)
    product = await _make_product(db, test_brand.id, cat.id, "Burger", 1500)

    override = SiteProductOverride(
        id=uuid.uuid4(),
        site_id=test_site.id,
        product_id=product.id,
        override_price_cents=999,
        is_excluded=False,
    )
    db.add(override)
    await db.commit()

    results = await resolve_products_for_site(db, test_brand.id, test_site.id)

    match = next(r for r in results if r.product_id == product.id)
    assert match.effective_price_cents == 999


async def test_resolver_excludes_excluded_products(db, test_brand, test_site):
    """Products with is_excluded=True do not appear in the resolved list."""
    cat = await _make_category(db, test_brand.id)
    visible = await _make_product(db, test_brand.id, cat.id, "Visible", 1000)
    hidden = await _make_product(db, test_brand.id, cat.id, "Hidden", 2000)

    override = SiteProductOverride(
        id=uuid.uuid4(),
        site_id=test_site.id,
        product_id=hidden.id,
        override_price_cents=None,
        is_excluded=True,
    )
    db.add(override)
    await db.commit()

    results = await resolve_products_for_site(db, test_brand.id, test_site.id)
    result_ids = {str(r.product_id) for r in results}

    assert str(visible.id) in result_ids
    assert str(hidden.id) not in result_ids


async def test_resolver_category_filter(db, test_brand, test_site):
    """When category_id is provided, only products from that category are returned."""
    cat_a = await _make_category(db, test_brand.id, "Category A")
    cat_b = await _make_category(db, test_brand.id, "Category B")
    p_a = await _make_product(db, test_brand.id, cat_a.id, "In A", 1000)
    _p_b = await _make_product(db, test_brand.id, cat_b.id, "In B", 2000)
    await db.commit()

    results = await resolve_products_for_site(db, test_brand.id, test_site.id, category_id=cat_a.id)

    assert len(results) == 1
    assert results[0].product_id == p_a.id


async def test_resolver_mixed_overrides(db, test_brand, test_site):
    """Mix of overridden, excluded, and base-price products resolves correctly."""
    cat = await _make_category(db, test_brand.id)
    base = await _make_product(db, test_brand.id, cat.id, "Base", 1000)
    overridden = await _make_product(db, test_brand.id, cat.id, "Override", 2000)
    excluded = await _make_product(db, test_brand.id, cat.id, "Excluded", 3000)

    db.add(SiteProductOverride(
        id=uuid.uuid4(), site_id=test_site.id, product_id=overridden.id,
        override_price_cents=1500, is_excluded=False,
    ))
    db.add(SiteProductOverride(
        id=uuid.uuid4(), site_id=test_site.id, product_id=excluded.id,
        override_price_cents=None, is_excluded=True,
    ))
    await db.commit()

    results = await resolve_products_for_site(db, test_brand.id, test_site.id)
    result_map = {str(r.product_id): r for r in results}

    assert str(base.id) in result_map
    assert result_map[str(base.id)].effective_price_cents == 1000

    assert str(overridden.id) in result_map
    assert result_map[str(overridden.id)].effective_price_cents == 1500

    assert str(excluded.id) not in result_map


async def test_resolver_inactive_products_excluded(db, test_brand, test_site):
    """Inactive products are not included in the resolved catalog."""
    cat = await _make_category(db, test_brand.id)
    active = await _make_product(db, test_brand.id, cat.id, "Active", 1000)
    inactive = Product(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        category_id=cat.id,
        name="Inactive",
        base_price_cents=500,
        display_order=0,
        is_active=False,
    )
    db.add(inactive)
    await db.commit()

    results = await resolve_products_for_site(db, test_brand.id, test_site.id)
    result_ids = {str(r.product_id) for r in results}

    assert str(active.id) in result_ids
    assert str(inactive.id) not in result_ids
