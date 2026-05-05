"""Site product override routes and resolved catalog endpoint."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.product import ResolvedProduct, SiteProductOverrideResponse, SiteProductOverrideSet
from app.services import site_override_service
from app.services.product_resolver import resolve_products_for_site
from app.utils.dependencies import POSAccess, resolve_access

router = APIRouter(prefix="/site-overrides", tags=["site-overrides"])


@router.get(
    "/{site_id}/catalog",
    response_model=list[ResolvedProduct],
    status_code=status.HTTP_200_OK,
)
async def get_resolved_catalog(
    site_id: uuid.UUID,
    category_id: uuid.UUID | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> list[ResolvedProduct]:
    """
    Return the resolved product catalog for a site.

    Applies price overrides and exclusions in a single joined query.
    Used by the Android app to load the POS catalog screen and by the
    invoice engine to price line items.

    Args:
        site_id: The site whose catalog to resolve.
        category_id: Optional category filter.
        skip: Pagination offset.
        limit: Maximum products to return.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        list[ResolvedProduct]: Products visible to the site with effective prices.
    """
    return await resolve_products_for_site(
        db, access.user.brand_id, site_id, category_id
    )


@router.put(
    "/{site_id}/{product_id}",
    response_model=SiteProductOverrideResponse,
    status_code=status.HTTP_200_OK,
)
async def set_override(
    site_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: SiteProductOverrideSet,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> SiteProductOverrideResponse:
    """
    Create or update a site product override (upsert).

    Sets a price override and/or excludes a product from a site's catalog.
    Sending is_excluded=True hides the product; setting override_price_cents
    charges a different price.

    Args:
        site_id: The site to apply the override for.
        product_id: The product to override.
        payload: Override data.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        SiteProductOverrideResponse: The created or updated override.
    """
    override = await site_override_service.set_override(
        db, access.user.brand_id, site_id, product_id, payload, access.user
    )
    return SiteProductOverrideResponse.model_validate(override)


@router.delete(
    "/{site_id}/{product_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_override(
    site_id: uuid.UUID,
    product_id: uuid.UUID,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove a site product override, restoring brand defaults.

    Args:
        site_id: The site whose override to remove.
        product_id: The product whose override to remove.
        access: Resolved POS access.
        db: Active database session.
    """
    await site_override_service.remove_override(
        db, access.user.brand_id, site_id, product_id, access.user
    )
