"""Modifier routes — modifier groups, options, and product links."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.modifier_service import (
    ModifierGroupCreate,
    ModifierGroupResponse,
    ModifierGroupUpdate,
    ModifierOptionCreate,
    ModifierOptionResponse,
    ModifierOptionUpdate,
    create_modifier_group,
    create_modifier_option,
    link_modifier_group,
    list_modifier_groups,
    list_modifier_options,
    unlink_modifier_group,
    update_modifier_group,
    update_modifier_option,
)
from app.utils.dependencies import POSAccess, resolve_access

router = APIRouter(tags=["modifiers"])


# ── Modifier group routes ─────────────────────────────────────────────────────


@router.get(
    "/modifier-groups",
    response_model=list[ModifierGroupResponse],
    status_code=status.HTTP_200_OK,
)
async def list_brand_modifier_groups(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> list[ModifierGroupResponse]:
    """
    List active modifier groups for the authenticated user's brand.

    Args:
        skip: Pagination offset.
        limit: Maximum rows to return.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        list[ModifierGroupResponse]: Active modifier groups ordered by name.
    """
    groups = await list_modifier_groups(db, access.user.brand_id, skip, limit)
    return [ModifierGroupResponse.model_validate(g) for g in groups]


@router.post(
    "/modifier-groups",
    response_model=ModifierGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_brand_modifier_group(
    payload: ModifierGroupCreate,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> ModifierGroupResponse:
    """
    Create a modifier group for the authenticated user's brand.

    Args:
        payload: Modifier group creation data.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        ModifierGroupResponse: The newly created modifier group.
    """
    group = await create_modifier_group(db, access.user.brand_id, payload, access.user)
    return ModifierGroupResponse.model_validate(group)


@router.patch(
    "/modifier-groups/{group_id}",
    response_model=ModifierGroupResponse,
    status_code=status.HTTP_200_OK,
)
async def update_brand_modifier_group(
    group_id: uuid.UUID,
    payload: ModifierGroupUpdate,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> ModifierGroupResponse:
    """
    Update a modifier group's mutable fields.

    Args:
        group_id: UUID of the modifier group to update.
        payload: Fields to update.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        ModifierGroupResponse: The updated modifier group.
    """
    group = await update_modifier_group(db, access.user.brand_id, group_id, payload, access.user)
    return ModifierGroupResponse.model_validate(group)


# ── Modifier option routes ────────────────────────────────────────────────────


@router.get(
    "/modifier-groups/{group_id}/options",
    response_model=list[ModifierOptionResponse],
    status_code=status.HTTP_200_OK,
)
async def list_group_options(
    group_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> list[ModifierOptionResponse]:
    """
    List active options for a modifier group.

    Args:
        group_id: UUID of the modifier group.
        skip: Pagination offset.
        limit: Maximum rows to return.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        list[ModifierOptionResponse]: Active options ordered by display_order then name.
    """
    options = await list_modifier_options(db, access.user.brand_id, group_id, skip, limit)
    return [ModifierOptionResponse.model_validate(o) for o in options]


@router.post(
    "/modifier-groups/{group_id}/options",
    response_model=ModifierOptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_group_option(
    group_id: uuid.UUID,
    payload: ModifierOptionCreate,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> ModifierOptionResponse:
    """
    Create a modifier option within a group.

    Args:
        group_id: UUID of the parent modifier group.
        payload: Option creation data.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        ModifierOptionResponse: The newly created option.
    """
    option = await create_modifier_option(db, access.user.brand_id, group_id, payload, access.user)
    return ModifierOptionResponse.model_validate(option)


@router.patch(
    "/modifier-options/{option_id}",
    response_model=ModifierOptionResponse,
    status_code=status.HTTP_200_OK,
)
async def update_group_option(
    option_id: uuid.UUID,
    payload: ModifierOptionUpdate,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> ModifierOptionResponse:
    """
    Update a modifier option's mutable fields.

    Args:
        option_id: UUID of the modifier option to update.
        payload: Fields to update.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        ModifierOptionResponse: The updated option.
    """
    option = await update_modifier_option(db, access.user.brand_id, option_id, payload, access.user)
    return ModifierOptionResponse.model_validate(option)


# ── Product–modifier link routes ──────────────────────────────────────────────


class _LinkBody:
    """Internal model for link request body — avoids circular import."""

    pass


from pydantic import BaseModel, Field


class ModifierLinkCreate(BaseModel):
    """Payload for linking a modifier group to a product."""

    modifier_group_id: uuid.UUID
    display_order: int = Field(0, ge=0)


class ModifierLinkResponse(BaseModel):
    """Response for a product–modifier group link."""

    id: uuid.UUID
    product_id: uuid.UUID
    modifier_group_id: uuid.UUID
    display_order: int

    model_config = {"from_attributes": True}


@router.post(
    "/products/{product_id}/modifiers",
    response_model=ModifierLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def link_product_modifier(
    product_id: uuid.UUID,
    payload: ModifierLinkCreate,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> ModifierLinkResponse:
    """
    Attach a modifier group to a product.

    Args:
        product_id: UUID of the product.
        payload: Modifier group to link and its display order.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        ModifierLinkResponse: The created link row.
    """
    link = await link_modifier_group(
        db,
        access.user.brand_id,
        product_id,
        payload.modifier_group_id,
        payload.display_order,
        access.user,
    )
    return ModifierLinkResponse.model_validate(link)


@router.delete(
    "/products/{product_id}/modifiers/{group_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_product_modifier(
    product_id: uuid.UUID,
    group_id: uuid.UUID,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove a modifier group from a product.

    Args:
        product_id: UUID of the product.
        group_id: UUID of the modifier group to unlink.
        access: Resolved POS access.
        db: Active database session.
    """
    await unlink_modifier_group(db, access.user.brand_id, product_id, group_id, access.user)
