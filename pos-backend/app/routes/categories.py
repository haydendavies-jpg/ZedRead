"""Category management routes — list, create, and update product categories.

Accessible to management JWT users and portal admins via resolve_catalog_access.
POS terminal JWT users can list categories (read-only); write operations require
management or portal JWT. All business logic lives in category_service.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.services import category_service
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(prefix="/categories", tags=["categories"])


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
    cats = await category_service.list_categories(db, effective_brand_id, skip, limit)
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
    cat = await category_service.create_category(db, effective_brand_id, payload, access.actor_user)
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
    cat = await category_service.update_category(db, effective_brand_id, category_id, payload, access.actor_user)
    return CategoryOut.model_validate(cat)
