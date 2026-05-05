"""Combo routes — product combo groups and combo options."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.combo_service import (
    ComboGroupCreate,
    ComboGroupResponse,
    ComboOptionCreate,
    ComboOptionResponse,
    add_combo_option,
    create_combo_group,
    list_combo_groups,
    list_combo_options,
    remove_combo_option,
)
from app.utils.dependencies import POSAccess, resolve_access

router = APIRouter(prefix="/products/{product_id}/combos", tags=["combos"])


@router.get(
    "/groups",
    response_model=list[ComboGroupResponse],
    status_code=status.HTTP_200_OK,
)
async def list_product_combo_groups(
    product_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> list[ComboGroupResponse]:
    """
    List combo groups for a product.

    Args:
        product_id: UUID of the parent product.
        skip: Pagination offset.
        limit: Maximum rows to return.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        list[ComboGroupResponse]: Combo groups ordered by display_order.
    """
    groups = await list_combo_groups(db, access.user.brand_id, product_id, skip, limit)
    return [ComboGroupResponse.model_validate(g) for g in groups]


@router.post(
    "/groups",
    response_model=ComboGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_product_combo_group(
    product_id: uuid.UUID,
    payload: ComboGroupCreate,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> ComboGroupResponse:
    """
    Create a combo group for a product.

    Args:
        product_id: UUID of the parent product.
        payload: Combo group creation data.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        ComboGroupResponse: The newly created combo group.
    """
    group = await create_combo_group(db, access.user.brand_id, product_id, payload, access.user)
    return ComboGroupResponse.model_validate(group)


@router.get(
    "/groups/{group_id}/options",
    response_model=list[ComboOptionResponse],
    status_code=status.HTTP_200_OK,
)
async def list_combo_group_options(
    product_id: uuid.UUID,
    group_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> list[ComboOptionResponse]:
    """
    List options for a combo group.

    Args:
        product_id: UUID of the parent product (used for URL consistency).
        group_id: UUID of the combo group.
        skip: Pagination offset.
        limit: Maximum rows to return.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        list[ComboOptionResponse]: Options ordered by display_order.
    """
    options = await list_combo_options(db, group_id, skip, limit)
    return [ComboOptionResponse.model_validate(o) for o in options]


@router.post(
    "/groups/{group_id}/options",
    response_model=ComboOptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_combo_group_option(
    product_id: uuid.UUID,
    group_id: uuid.UUID,
    payload: ComboOptionCreate,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> ComboOptionResponse:
    """
    Add a product as an option to a combo group.

    Args:
        product_id: UUID of the parent product (used for URL consistency).
        group_id: UUID of the combo group to add the option to.
        payload: Option data (product_id, price_delta_cents).
        access: Resolved POS access.
        db: Active database session.

    Returns:
        ComboOptionResponse: The created option.
    """
    option = await add_combo_option(db, access.user.brand_id, group_id, payload, access.user)
    return ComboOptionResponse.model_validate(option)


@router.delete(
    "/groups/{group_id}/options/{option_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_combo_group_option(
    product_id: uuid.UUID,
    group_id: uuid.UUID,
    option_id: uuid.UUID,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove an option from a combo group.

    Args:
        product_id: UUID of the parent product (used for URL consistency).
        group_id: UUID of the combo group (used for URL consistency).
        option_id: UUID of the option to remove.
        access: Resolved POS access.
        db: Active database session.
    """
    await remove_combo_option(db, access.user.brand_id, option_id, access.user)
