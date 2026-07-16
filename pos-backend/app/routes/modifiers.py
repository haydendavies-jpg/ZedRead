"""Modifier routes — modifier groups, options, and product links."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.modifier_service import (
    ModifierGroupCreate,
    ModifierGroupDetail,
    ModifierGroupProductItem,
    ModifierGroupResponse,
    ModifierGroupUpdate,
    ModifierOptionCreate,
    ModifierOptionLinkCreate,
    ModifierOptionResponse,
    ModifierOptionUpdate,
    ProductModifiersOut,
    ProductModifiersReorderRequest,
    create_modifier_group,
    create_modifier_option,
    deactivate_modifier_group,
    deactivate_modifier_option,
    duplicate_modifier_group,
    link_modifier_group,
    link_option_group,
    list_modifier_groups,
    list_modifier_groups_detailed,
    list_modifier_options,
    list_product_modifiers,
    list_products_for_modifier_group,
    sync_product_modifier_groups,
    unlink_modifier_group,
    unlink_option_group,
    update_modifier_group,
    update_modifier_option,
)
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(tags=["modifiers"])


# ── Modifier group routes ─────────────────────────────────────────────────────


@router.get(
    "/modifier-groups",
    response_model=list[ModifierGroupResponse],
    status_code=status.HTTP_200_OK,
)
async def list_brand_modifier_groups(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[ModifierGroupResponse]:
    """
    List active modifier groups for the authenticated user's brand.

    Args:
        skip: Pagination offset.
        limit: Maximum rows to return.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        list[ModifierGroupResponse]: Active modifier groups ordered by name.
    """
    groups = await list_modifier_groups(db, access.effective_brand_id(brand_id), skip, limit)
    return [ModifierGroupResponse.model_validate(g) for g in groups]


@router.post(
    "/modifier-groups",
    response_model=ModifierGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_brand_modifier_group(
    payload: ModifierGroupCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ModifierGroupResponse:
    """
    Create a modifier group for the authenticated user's brand.

    Args:
        payload: Modifier group creation data.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ModifierGroupResponse: The newly created modifier group.
    """
    group = await create_modifier_group(db, access.effective_brand_id(brand_id), payload, access.actor_user)
    return ModifierGroupResponse.model_validate(group)


@router.patch(
    "/modifier-groups/{group_id}",
    response_model=ModifierGroupResponse,
    status_code=status.HTTP_200_OK,
)
async def update_brand_modifier_group(
    group_id: uuid.UUID,
    payload: ModifierGroupUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ModifierGroupResponse:
    """
    Update a modifier group's mutable fields.

    Args:
        group_id: UUID of the modifier group to update.
        payload: Fields to update.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ModifierGroupResponse: The updated modifier group.
    """
    group = await update_modifier_group(db, access.effective_brand_id(brand_id), group_id, payload, access.actor_user)
    return ModifierGroupResponse.model_validate(group)


@router.get(
    "/modifier-groups/detailed",
    response_model=list[ModifierGroupDetail],
    status_code=status.HTTP_200_OK,
)
async def list_brand_modifier_groups_detailed(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[ModifierGroupDetail]:
    """
    List active modifier groups for a brand, nested with options, each
    option's comboing links, and a used-by-product count — powers the
    portal's Modifiers tab in one call.

    Args:
        skip: Pagination offset.
        limit: Maximum rows to return.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        list[ModifierGroupDetail]: Active modifier groups, fully nested.
    """
    return await list_modifier_groups_detailed(db, access.effective_brand_id(brand_id), skip, limit)


@router.post(
    "/modifier-groups/{group_id}/duplicate",
    response_model=ModifierGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_brand_modifier_group(
    group_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ModifierGroupResponse:
    """
    Duplicate a modifier group and its active options.

    Args:
        group_id: UUID of the modifier group to duplicate.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ModifierGroupResponse: The newly created copy.
    """
    group = await duplicate_modifier_group(db, access.effective_brand_id(brand_id), group_id, access.actor_user)
    return ModifierGroupResponse.model_validate(group)


@router.delete(
    "/modifier-groups/{group_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def deactivate_brand_modifier_group(
    group_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Soft-delete a modifier group.

    Args:
        group_id: UUID of the modifier group to deactivate.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.
    """
    await deactivate_modifier_group(db, access.effective_brand_id(brand_id), group_id, access.actor_user)


# ── Used-by-products routes ───────────────────────────────────────────────────


@router.get(
    "/modifier-groups/{modifier_group_id}/products",
    response_model=list[ModifierGroupProductItem],
    status_code=status.HTTP_200_OK,
)
async def list_modifier_group_products(
    modifier_group_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[ModifierGroupProductItem]:
    """
    List the products currently linked to a modifier group.

    Powers the "used by products" expand on the Modifiers tab card; adding a
    product from this screen reuses the existing
    POST /products/{product_id}/modifiers route with this group's id.

    Args:
        modifier_group_id: UUID of the modifier group.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        list[ModifierGroupProductItem]: Linked products ordered by name.
    """
    products = await list_products_for_modifier_group(
        db, access.effective_brand_id(brand_id), modifier_group_id
    )
    return [ModifierGroupProductItem.model_validate(p) for p in products]


# ── Modifier option routes ────────────────────────────────────────────────────


@router.get(
    "/modifier-groups/{group_id}/options",
    response_model=list[ModifierOptionResponse],
    status_code=status.HTTP_200_OK,
)
async def list_group_options(
    group_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[ModifierOptionResponse]:
    """
    List active options for a modifier group.

    Args:
        group_id: UUID of the modifier group.
        skip: Pagination offset.
        limit: Maximum rows to return.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        list[ModifierOptionResponse]: Active options ordered by display_order then name.
    """
    options = await list_modifier_options(db, access.effective_brand_id(brand_id), group_id, skip, limit)
    return [ModifierOptionResponse.model_validate(o) for o in options]


@router.post(
    "/modifier-groups/{group_id}/options",
    response_model=ModifierOptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_group_option(
    group_id: uuid.UUID,
    payload: ModifierOptionCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ModifierOptionResponse:
    """
    Create a modifier option within a group.

    Args:
        group_id: UUID of the parent modifier group.
        payload: Option creation data.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ModifierOptionResponse: The newly created option.
    """
    option = await create_modifier_option(db, access.effective_brand_id(brand_id), group_id, payload, access.actor_user)
    return ModifierOptionResponse.model_validate(option)


@router.patch(
    "/modifier-options/{option_id}",
    response_model=ModifierOptionResponse,
    status_code=status.HTTP_200_OK,
)
async def update_group_option(
    option_id: uuid.UUID,
    payload: ModifierOptionUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ModifierOptionResponse:
    """
    Update a modifier option's mutable fields.

    Args:
        option_id: UUID of the modifier option to update.
        payload: Fields to update.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ModifierOptionResponse: The updated option.
    """
    option = await update_modifier_option(db, access.effective_brand_id(brand_id), option_id, payload, access.actor_user)
    return ModifierOptionResponse.model_validate(option)


@router.delete(
    "/modifier-options/{option_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def deactivate_group_option(
    option_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Soft-delete a modifier option.

    Args:
        option_id: UUID of the modifier option to deactivate.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.
    """
    await deactivate_modifier_option(db, access.effective_brand_id(brand_id), option_id, access.actor_user)


# ── Comboing — option → linked group routes ───────────────────────────────────


@router.post(
    "/modifier-options/{option_id}/links",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def link_option_to_group(
    option_id: uuid.UUID,
    payload: ModifierOptionLinkCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Link a modifier option to another modifier group it expands into ("comboing").

    Args:
        option_id: UUID of the option that will surface the linked group.
        payload: Which group to link and its display order.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.
    """
    await link_option_group(db, access.effective_brand_id(brand_id), option_id, payload, access.actor_user)


@router.delete(
    "/modifier-options/{option_id}/links/{linked_group_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_option_from_group(
    option_id: uuid.UUID,
    linked_group_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove a comboing link between an option and a linked group.

    Args:
        option_id: UUID of the option.
        linked_group_id: UUID of the linked modifier group to unlink.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.
    """
    await unlink_option_group(db, access.effective_brand_id(brand_id), option_id, linked_group_id, access.actor_user)


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


@router.get(
    "/products/{product_id}/modifiers",
    response_model=ProductModifiersOut,
    status_code=status.HTTP_200_OK,
)
async def list_product_modifier_groups(
    product_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ProductModifiersOut:
    """
    List a product's attached modifier groups (ordered) and available ones to attach.

    Args:
        product_id: UUID of the product.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ProductModifiersOut: attached (ordered) and available modifier groups.
    """
    return await list_product_modifiers(db, access.effective_brand_id(brand_id), product_id)


@router.post(
    "/products/{product_id}/modifiers",
    response_model=ModifierLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def link_product_modifier(
    product_id: uuid.UUID,
    payload: ModifierLinkCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ModifierLinkResponse:
    """
    Attach a modifier group to a product.

    Args:
        product_id: UUID of the product.
        payload: Modifier group to link and its display order.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ModifierLinkResponse: The created link row.
    """
    link = await link_modifier_group(
        db,
        access.effective_brand_id(brand_id),
        product_id,
        payload.modifier_group_id,
        payload.display_order,
        access.actor_user,
    )
    return ModifierLinkResponse.model_validate(link)


@router.patch(
    "/products/{product_id}/modifiers/reorder",
    response_model=ProductModifiersOut,
    status_code=status.HTTP_200_OK,
)
async def reorder_product_modifier_groups(
    product_id: uuid.UUID,
    payload: ProductModifiersReorderRequest,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ProductModifiersOut:
    """
    Reconcile a product's attached modifier groups to the full ordered set given.

    Attaches any id in modifier_group_ids not currently attached, detaches any
    currently-attached id missing from the list, and resequences display_order
    to match list index — all in one transaction.

    Args:
        product_id: UUID of the product.
        payload: The full desired attached set, in order.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ProductModifiersOut: The product's attached/available groups after the sync.
    """
    return await sync_product_modifier_groups(
        db,
        access.effective_brand_id(brand_id),
        product_id,
        payload.modifier_group_ids,
        access.actor_user,
    )


@router.delete(
    "/products/{product_id}/modifiers/{group_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_product_modifier(
    product_id: uuid.UUID,
    group_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove a modifier group from a product.

    Args:
        product_id: UUID of the product.
        group_id: UUID of the modifier group to unlink.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.
    """
    await unlink_modifier_group(db, access.effective_brand_id(brand_id), product_id, group_id, access.actor_user)
