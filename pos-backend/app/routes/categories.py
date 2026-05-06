"""Category management routes — list and create product categories.

Accessible to management JWT users and portal admins via resolve_catalog_access.
POS terminal JWT users can list categories (read-only); write operations require
management or portal JWT.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import PRODUCT_CREATED, PRODUCT_UPDATED
from app.constants.statuses import ActorType
from app.database import get_db
from app.models.category import Category
from app.services.audit_service import log_action
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryResponse:
    """Pydantic-free response helper — categories use simple dict serialisation."""
    pass


from pydantic import BaseModel


class CategoryOut(BaseModel):
    """Serialised category for API responses."""

    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    is_system: bool
    is_active: bool
    display_order: int

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    """Payload for creating a new product category."""

    name: str
    brand_id: uuid.UUID
    display_order: int = 0


class CategoryUpdate(BaseModel):
    """Payload for updating a category's mutable fields."""

    name: str | None = None
    display_order: int | None = None
    is_active: bool | None = None


@router.get("", response_model=list[CategoryOut], status_code=status.HTTP_200_OK)
async def list_categories(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[CategoryOut]:
    """
    List active categories for the authenticated user's brand.

    Args:
        skip: Pagination offset.
        limit: Maximum number of categories to return.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        list[CategoryOut]: Active categories ordered by display_order.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    result = await db.execute(
        select(Category)
        .where(Category.brand_id == effective_brand_id, Category.is_active == True)  # noqa: E712
        .order_by(Category.display_order, Category.name)
        .offset(skip)
        .limit(limit)
    )
    cats = result.scalars().all()
    return [CategoryOut.model_validate(c) for c in cats]


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> CategoryOut:
    """
    Create a new product category.

    Args:
        payload: Category creation data.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        CategoryOut: The created category.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Category management requires a management or portal JWT",
        )
    effective_brand_id = access.effective_brand_id(brand_id)
    cat = Category(
        id=uuid.uuid4(),
        brand_id=effective_brand_id,
        name=payload.name,
        display_order=payload.display_order,
        is_system=False,
        is_active=True,
    )
    db.add(cat)
    await log_action(
        db=db,
        action=PRODUCT_CREATED,
        entity_type="category",
        entity_id=str(cat.id),
        actor_type=ActorType.USER,
        actor_id=access.actor_user.id,
        actor_email=access.actor_user.email,
        actor_name=access.actor_user.name,
        after_state={"name": payload.name},
    )
    await db.commit()
    await db.refresh(cat)
    return CategoryOut.model_validate(cat)


@router.patch("/{category_id}", response_model=CategoryOut, status_code=status.HTTP_200_OK)
async def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> CategoryOut:
    """
    Update a category's mutable fields.

    System categories cannot be renamed or deactivated.

    Args:
        category_id: UUID of the category to update.
        payload: Fields to update.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        CategoryOut: The updated category.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Category management requires a management or portal JWT",
        )
    effective_brand_id = access.effective_brand_id(brand_id)
    result = await db.execute(
        select(Category).where(Category.id == category_id, Category.brand_id == effective_brand_id)
    )
    cat = result.scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    if cat.is_system and (payload.name is not None or payload.is_active is False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System categories cannot be renamed or deactivated",
        )

    before: dict = {}
    if payload.name is not None:
        before["name"] = cat.name
        cat.name = payload.name
    if payload.display_order is not None:
        before["display_order"] = cat.display_order
        cat.display_order = payload.display_order
    if payload.is_active is not None:
        before["is_active"] = cat.is_active
        cat.is_active = payload.is_active

    await log_action(
        db=db,
        action=PRODUCT_UPDATED,
        entity_type="category",
        entity_id=str(cat.id),
        actor_type=ActorType.USER,
        actor_id=access.actor_user.id,
        actor_email=access.actor_user.email,
        actor_name=access.actor_user.name,
        before_state=before,
        after_state=payload.model_dump(exclude_none=True),
    )
    await db.commit()
    await db.refresh(cat)
    return CategoryOut.model_validate(cat)
