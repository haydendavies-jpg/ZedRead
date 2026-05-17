"""Product resolver: merges brand catalog with site-level overrides.

resolve_products_for_site() returns a list of ResolvedProduct — the view
of the catalog as a specific site sees it.  It:
  - Excludes products where is_excluded=True in the site's override row
  - Applies override_price_cents when set, otherwise uses base_price_cents
  - Uses a single joined query — no N+1 (critical for Stage 10 invoice engine)

The ResolvedProduct schema is the stable contract between this resolver and
the invoice engine (Stage 10).  Do not change field names without updating
both this module and the invoice service.
"""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.site_product_override import SiteProductOverride
from app.schemas.product import ResolvedProduct

log = structlog.get_logger(__name__)


async def resolve_products_for_site(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID,
    category_id: uuid.UUID | None = None,
) -> list[ResolvedProduct]:
    """
    Return the product catalog for a site with overrides merged in.

    Fetches all active brand products with a single LEFT OUTER JOIN on
    site_product_overrides.  Products with is_excluded=True for this site
    are filtered out after the join.

    Args:
        db: Active database session.
        brand_id: Brand whose products to resolve.
        site_id: Site to apply overrides for.
        category_id: Optional filter — only products in this category.

    Returns:
        list[ResolvedProduct]: Products visible to the site with effective
        prices applied, ordered by display_order then name.
    """
    query = (
        select(Product, SiteProductOverride)
        .outerjoin(
            SiteProductOverride,
            (SiteProductOverride.product_id == Product.id)
            & (SiteProductOverride.site_id == site_id),
        )
        .where(
            Product.brand_id == brand_id,
            Product.is_active == True,  # noqa: E712
        )
        .order_by(Product.display_order, Product.name)
    )

    if category_id is not None:
        query = query.where(Product.category_id == category_id)

    result = await db.execute(query)
    rows = result.all()

    resolved: list[ResolvedProduct] = []
    for product, override in rows:
        # Skip products explicitly excluded for this site
        if override is not None and override.is_excluded:
            continue

        # Apply price override if present, otherwise use base price
        effective_price = (
            override.override_price_cents
            if override is not None and override.override_price_cents is not None
            else product.base_price_cents
        )

        resolved.append(
            ResolvedProduct(
                product_id=product.id,
                name=product.name,
                category_id=product.category_id,
                tax_category_id=product.tax_category_id,
                effective_price_cents=effective_price,
                photo_url=product.photo_url,
                display_order=product.display_order,
            )
        )

    log.debug(
        "product_resolver.resolved",
        brand_id=str(brand_id),
        site_id=str(site_id),
        total=len(resolved),
    )
    return resolved
