"""Business logic for tax category and tax rate CRUD."""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    TAX_CATEGORY_CREATED,
    TAX_CATEGORY_UPDATED,
    TAX_RATE_CREATED,
    TAX_RATE_UPDATED,
)
from app.constants.statuses import ActorType
from app.models.superadmin import SuperAdmin
from app.models.user import User
from app.models.tax_category import TaxCategory
from app.models.tax_rate import TaxRate
from app.schemas.tax import (
    TaxCategoryCreate,
    TaxCategoryResponse,
    TaxCategoryUpdate,
    TaxRateCreate,
    TaxRateResponse,
    TaxRateUpdate,
)
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


async def _get_category_or_404(
    db: AsyncSession, brand_id: uuid.UUID, tax_category_id: uuid.UUID
) -> TaxCategory:
    """
    Fetch a TaxCategory by ID scoped to a brand, or raise HTTP 404.

    Args:
        db: Active database session.
        brand_id: Brand scope — prevents cross-brand access.
        tax_category_id: The UUID of the tax category to fetch.

    Returns:
        TaxCategory: The found instance.

    Raises:
        HTTPException: 404 if not found within the brand.
    """
    result = await db.execute(
        select(TaxCategory).where(
            TaxCategory.id == tax_category_id,
            TaxCategory.brand_id == brand_id,
        )
    )
    cat = result.scalar_one_or_none()
    if cat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tax category not found",
        )
    return cat


async def list_tax_categories(
    db: AsyncSession,
    brand_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
) -> list[TaxCategory]:
    """
    Return a paginated list of active tax categories for a brand.

    Args:
        db: Active database session.
        brand_id: Scope to this brand.
        skip: Pagination offset.
        limit: Maximum rows to return.

    Returns:
        list[TaxCategory]: Active categories in insertion order.
    """
    result = await db.execute(
        select(TaxCategory)
        .where(TaxCategory.brand_id == brand_id, TaxCategory.is_active == True)  # noqa: E712
        .order_by(TaxCategory.created_at)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def create_tax_category(
    db: AsyncSession,
    brand_id: uuid.UUID,
    payload: TaxCategoryCreate,
    actor: User | SuperAdmin,
) -> TaxCategory:
    """
    Create a new TaxCategory for a brand and write an audit log row.

    Args:
        db: Active database session.
        brand_id: The brand to create the category under.
        payload: Creation data (name).
        actor: The authenticated POS user performing the action.

    Returns:
        TaxCategory: The newly created instance.
    """
    cat = TaxCategory(
        id=uuid.uuid4(),
        brand_id=brand_id,
        name=payload.name,
        is_active=True,
    )
    db.add(cat)

    await log_action(
        db=db,
        action=TAX_CATEGORY_CREATED,
        entity_type="tax_category",
        entity_id=str(cat.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"name": cat.name, "brand_id": str(brand_id)},
    )

    await db.commit()
    await db.refresh(cat)
    log.info("tax_category.created", tax_category_id=str(cat.id), brand_id=str(brand_id))
    return cat


async def update_tax_category(
    db: AsyncSession,
    brand_id: uuid.UUID,
    tax_category_id: uuid.UUID,
    payload: TaxCategoryUpdate,
    actor: User | SuperAdmin,
) -> TaxCategory:
    """
    Update a TaxCategory's mutable fields.

    Args:
        db: Active database session.
        brand_id: Brand scope for the lookup.
        tax_category_id: UUID of the category to update.
        payload: Fields to update (all optional).
        actor: The authenticated POS user performing the action.

    Returns:
        TaxCategory: The updated instance.

    Raises:
        HTTPException: 404 if not found within the brand.
    """
    cat = await _get_category_or_404(db, brand_id, tax_category_id)
    before = {"name": cat.name}

    if payload.name is not None:
        cat.name = payload.name

    await log_action(
        db=db,
        action=TAX_CATEGORY_UPDATED,
        entity_type="tax_category",
        entity_id=str(cat.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state={"name": cat.name},
    )

    await db.commit()
    await db.refresh(cat)
    return cat


async def list_tax_rates(
    db: AsyncSession,
    brand_id: uuid.UUID,
    tax_category_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
) -> list[TaxRate]:
    """
    Return a paginated list of active tax rates for a tax category.

    Args:
        db: Active database session.
        brand_id: Brand scope used to validate the tax category exists.
        tax_category_id: UUID of the parent tax category.
        skip: Pagination offset.
        limit: Maximum rows to return.

    Returns:
        list[TaxRate]: Active tax rates for the category.

    Raises:
        HTTPException: 404 if the tax category does not exist within the brand.
    """
    await _get_category_or_404(db, brand_id, tax_category_id)

    result = await db.execute(
        select(TaxRate)
        .where(
            TaxRate.tax_category_id == tax_category_id,
            TaxRate.is_active == True,  # noqa: E712
        )
        .order_by(TaxRate.created_at)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def create_tax_rate(
    db: AsyncSession,
    brand_id: uuid.UUID,
    tax_category_id: uuid.UUID,
    payload: TaxRateCreate,
    actor: User | SuperAdmin,
) -> TaxRate:
    """
    Create a TaxRate under a TaxCategory and write an audit log row.

    Args:
        db: Active database session.
        brand_id: Brand scope for the parent tax category lookup.
        tax_category_id: UUID of the parent tax category.
        payload: Rate data (name, rate_percent, tax_model).
        actor: The authenticated POS user performing the action.

    Returns:
        TaxRate: The newly created instance.

    Raises:
        HTTPException: 404 if the tax category does not exist within the brand.
    """
    await _get_category_or_404(db, brand_id, tax_category_id)

    rate = TaxRate(
        id=uuid.uuid4(),
        tax_category_id=tax_category_id,
        name=payload.name,
        rate_percent=payload.rate_percent,
        tax_model=payload.tax_model.value,
        is_active=True,
    )
    db.add(rate)

    await log_action(
        db=db,
        action=TAX_RATE_CREATED,
        entity_type="tax_rate",
        entity_id=str(rate.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "name": rate.name,
            "rate_percent": str(rate.rate_percent),
            "tax_model": rate.tax_model,
            "tax_category_id": str(tax_category_id),
        },
    )

    await db.commit()
    await db.refresh(rate)
    log.info("tax_rate.created", tax_rate_id=str(rate.id), tax_category_id=str(tax_category_id))
    return rate


async def update_tax_rate(
    db: AsyncSession,
    brand_id: uuid.UUID,
    tax_rate_id: uuid.UUID,
    payload: TaxRateUpdate,
    actor: User | SuperAdmin,
) -> TaxRate:
    """
    Update a TaxRate's mutable fields and write an audit log row.

    Args:
        db: Active database session.
        brand_id: Brand scope — used to verify the parent tax category.
        tax_rate_id: UUID of the rate to update.
        payload: Fields to update (all optional).
        actor: The authenticated POS user performing the action.

    Returns:
        TaxRate: The updated instance.

    Raises:
        HTTPException: 404 if the rate or its parent category does not exist.
    """
    # Fetch rate and validate it belongs to a category within the brand
    result = await db.execute(
        select(TaxRate)
        .join(TaxCategory, TaxRate.tax_category_id == TaxCategory.id)
        .where(
            TaxRate.id == tax_rate_id,
            TaxCategory.brand_id == brand_id,
        )
    )
    rate = result.scalar_one_or_none()
    if rate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tax rate not found",
        )

    before = {
        "name": rate.name,
        "rate_percent": str(rate.rate_percent),
        "tax_model": rate.tax_model,
    }

    if payload.name is not None:
        rate.name = payload.name
    if payload.rate_percent is not None:
        rate.rate_percent = payload.rate_percent
    if payload.tax_model is not None:
        rate.tax_model = payload.tax_model.value

    await log_action(
        db=db,
        action=TAX_RATE_UPDATED,
        entity_type="tax_rate",
        entity_id=str(rate.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state={
            "name": rate.name,
            "rate_percent": str(rate.rate_percent),
            "tax_model": rate.tax_model,
        },
    )

    await db.commit()
    await db.refresh(rate)
    return rate
