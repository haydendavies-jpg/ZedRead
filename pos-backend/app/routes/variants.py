"""Variant routes — product variants, attribute types, and attribute values."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.variant_service import (
    VariantCreate,
    VariantResponse,
    VariantUpdate,
    create_variant,
    deactivate_variant,
    list_variants,
    update_variant,
)
from app.utils.dependencies import POSAccess, resolve_access

router = APIRouter(prefix="/products/{product_id}/variants", tags=["variants"])


@router.get("", response_model=list[VariantResponse], status_code=status.HTTP_200_OK)
async def list_product_variants(
    product_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> list[VariantResponse]:
    """
    List active variants for a product.

    Args:
        product_id: UUID of the parent product.
        skip: Pagination offset.
        limit: Maximum rows to return.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        list[VariantResponse]: Active variants with attribute data.
    """
    return await list_variants(db, access.user.brand_id, product_id, skip, limit)


@router.post("", response_model=VariantResponse, status_code=status.HTTP_201_CREATED)
async def create_product_variant(
    product_id: uuid.UUID,
    payload: VariantCreate,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> VariantResponse:
    """
    Create a variant for a product.

    Args:
        product_id: UUID of the parent product.
        payload: Variant data including attribute assignments.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        VariantResponse: The newly created variant.
    """
    return await create_variant(db, access.user.brand_id, product_id, payload, access.user)


@router.patch("/{variant_id}", response_model=VariantResponse, status_code=status.HTTP_200_OK)
async def update_product_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    payload: VariantUpdate,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> VariantResponse:
    """
    Update a variant's price or SKU.

    Args:
        product_id: UUID of the parent product (used for URL consistency).
        variant_id: UUID of the variant to update.
        payload: Fields to update.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        VariantResponse: The updated variant.
    """
    return await update_variant(db, access.user.brand_id, variant_id, payload, access.user)


@router.delete("/{variant_id}", response_model=VariantResponse, status_code=status.HTTP_200_OK)
async def deactivate_product_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> VariantResponse:
    """
    Soft-delete a variant (set is_active=False).

    Args:
        product_id: UUID of the parent product (used for URL consistency).
        variant_id: UUID of the variant to deactivate.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        VariantResponse: The deactivated variant.
    """
    return await deactivate_variant(db, access.user.brand_id, variant_id, access.user)
