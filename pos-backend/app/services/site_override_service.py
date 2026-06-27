"""Business logic for site product override CRUD."""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import SITE_PRODUCT_OVERRIDE_REMOVED, SITE_PRODUCT_OVERRIDE_SET
from app.constants.statuses import ActorType
from app.models.superadmin import SuperAdmin
from app.models.pos_user import POSUser
from app.models.product import Product
from app.models.site import Site
from app.models.site_product_override import SiteProductOverride
from app.schemas.product import SiteProductOverrideSet
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


async def set_override(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: SiteProductOverrideSet,
    actor: POSUser | SuperAdmin,
) -> SiteProductOverride:
    """
    Create or update a site product override (upsert).

    Validates that both the site and product belong to the same brand before
    writing. If an override row already exists it is updated in place; otherwise
    a new row is inserted.

    Args:
        db: Active database session.
        brand_id: Brand scope — site and product must belong to this brand.
        site_id: The site to apply the override for.
        product_id: The product being overridden.
        payload: Override data (override_price_cents, is_excluded).
        actor: The authenticated POS user performing the action.

    Returns:
        SiteProductOverride: The created or updated override row.

    Raises:
        HTTPException: 404 if the site or product is not found within the brand.
    """
    # Validate site belongs to brand
    site_result = await db.execute(
        select(Site).where(Site.id == site_id, Site.brand_id == brand_id)
    )
    if site_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found within this brand",
        )

    # Validate product belongs to brand
    product_result = await db.execute(
        select(Product).where(Product.id == product_id, Product.brand_id == brand_id)
    )
    if product_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found within this brand",
        )

    # Upsert: update existing row or create new one
    existing_result = await db.execute(
        select(SiteProductOverride).where(
            SiteProductOverride.site_id == site_id,
            SiteProductOverride.product_id == product_id,
        )
    )
    override = existing_result.scalar_one_or_none()

    before_state = (
        {
            "override_price_cents": override.override_price_cents,
            "is_excluded": override.is_excluded,
        }
        if override
        else None
    )

    if override is not None:
        override.override_price_cents = payload.override_price_cents
        override.is_excluded = payload.is_excluded
    else:
        override = SiteProductOverride(
            id=uuid.uuid4(),
            site_id=site_id,
            product_id=product_id,
            override_price_cents=payload.override_price_cents,
            is_excluded=payload.is_excluded,
        )
        db.add(override)

    await log_action(
        db=db,
        action=SITE_PRODUCT_OVERRIDE_SET,
        entity_type="site_product_override",
        entity_id=str(override.id) if override.id else "pending",
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before_state,
        after_state={
            "site_id": str(site_id),
            "product_id": str(product_id),
            "override_price_cents": payload.override_price_cents,
            "is_excluded": payload.is_excluded,
        },
    )

    await db.commit()
    await db.refresh(override)
    log.info(
        "site_override.set",
        site_id=str(site_id),
        product_id=str(product_id),
    )
    return override


async def remove_override(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID,
    product_id: uuid.UUID,
    actor: POSUser | SuperAdmin,
) -> None:
    """
    Delete a site product override row.

    Args:
        db: Active database session.
        brand_id: Brand scope for validation.
        site_id: The site whose override to remove.
        product_id: The product whose override to remove.
        actor: The authenticated POS user performing the action.

    Raises:
        HTTPException: 404 if no override exists for this site+product.
    """
    result = await db.execute(
        select(SiteProductOverride)
        .join(Product, SiteProductOverride.product_id == Product.id)
        .where(
            SiteProductOverride.site_id == site_id,
            SiteProductOverride.product_id == product_id,
            Product.brand_id == brand_id,
        )
    )
    override = result.scalar_one_or_none()
    if override is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Override not found",
        )

    await log_action(
        db=db,
        action=SITE_PRODUCT_OVERRIDE_REMOVED,
        entity_type="site_product_override",
        entity_id=str(override.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={
            "site_id": str(site_id),
            "product_id": str(product_id),
            "override_price_cents": override.override_price_cents,
            "is_excluded": override.is_excluded,
        },
    )

    await db.delete(override)
    await db.commit()
    log.info("site_override.removed", site_id=str(site_id), product_id=str(product_id))
