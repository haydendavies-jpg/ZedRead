"""Business logic for modifier groups, modifier options, and product-modifier links."""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    MODIFIER_GROUP_CREATED,
    MODIFIER_GROUP_UPDATED,
    MODIFIER_OPTION_CREATED,
    MODIFIER_OPTION_UPDATED,
    PRODUCT_MODIFIER_LINKED,
    PRODUCT_MODIFIER_UNLINKED,
)
from app.constants.statuses import ActorType
from app.models.modifier_group import ModifierGroup
from app.models.modifier_option import ModifierOption
from app.models.pos_user import POSUser
from app.models.product import Product
from app.models.product_modifier_group_link import ProductModifierGroupLink
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


# ── Inline schemas ─────────────────────────────────────────────────────────────

from pydantic import BaseModel, Field


class ModifierGroupCreate(BaseModel):
    """Payload for creating a modifier group."""

    name: str = Field(..., min_length=1, max_length=100)
    min_selections: int = Field(0, ge=0)
    max_selections: int = Field(1, ge=1)


class ModifierGroupUpdate(BaseModel):
    """Payload for updating a modifier group — all optional."""

    name: str | None = Field(None, min_length=1, max_length=100)
    min_selections: int | None = Field(None, ge=0)
    max_selections: int | None = Field(None, ge=1)


class ModifierGroupResponse(BaseModel):
    """Response schema for a modifier group."""

    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    min_selections: int
    max_selections: int
    is_active: bool

    model_config = {"from_attributes": True}


class ModifierOptionCreate(BaseModel):
    """Payload for creating a modifier option."""

    name: str = Field(..., min_length=1, max_length=100)
    price_delta_cents: int = Field(0)
    display_order: int = Field(0, ge=0)


class ModifierOptionUpdate(BaseModel):
    """Payload for updating a modifier option — all optional."""

    name: str | None = Field(None, min_length=1, max_length=100)
    price_delta_cents: int | None = None
    display_order: int | None = Field(None, ge=0)


class ModifierOptionResponse(BaseModel):
    """Response schema for a modifier option."""

    id: uuid.UUID
    modifier_group_id: uuid.UUID
    name: str
    price_delta_cents: int
    display_order: int
    is_active: bool

    model_config = {"from_attributes": True}


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_group_or_404(
    db: AsyncSession, brand_id: uuid.UUID, group_id: uuid.UUID
) -> ModifierGroup:
    """Fetch a ModifierGroup scoped to a brand, or raise 404."""
    result = await db.execute(
        select(ModifierGroup).where(
            ModifierGroup.id == group_id,
            ModifierGroup.brand_id == brand_id,
        )
    )
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Modifier group not found")
    return group


async def _get_option_or_404(
    db: AsyncSession, brand_id: uuid.UUID, option_id: uuid.UUID
) -> ModifierOption:
    """Fetch a ModifierOption scoped to a brand via its group, or raise 404."""
    result = await db.execute(
        select(ModifierOption)
        .join(ModifierGroup, ModifierOption.modifier_group_id == ModifierGroup.id)
        .where(ModifierOption.id == option_id, ModifierGroup.brand_id == brand_id)
    )
    option = result.scalar_one_or_none()
    if option is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Modifier option not found")
    return option


# ── Modifier group operations ─────────────────────────────────────────────────


async def list_modifier_groups(
    db: AsyncSession,
    brand_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
) -> list[ModifierGroup]:
    """Return active modifier groups for a brand."""
    result = await db.execute(
        select(ModifierGroup)
        .where(ModifierGroup.brand_id == brand_id, ModifierGroup.is_active == True)  # noqa: E712
        .order_by(ModifierGroup.name)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def create_modifier_group(
    db: AsyncSession,
    brand_id: uuid.UUID,
    payload: ModifierGroupCreate,
    actor: POSUser,
) -> ModifierGroup:
    """Create a modifier group for a brand and write an audit row."""
    group = ModifierGroup(
        id=uuid.uuid4(),
        brand_id=brand_id,
        name=payload.name,
        min_selections=payload.min_selections,
        max_selections=payload.max_selections,
        is_active=True,
    )
    db.add(group)

    await log_action(
        db=db,
        action=MODIFIER_GROUP_CREATED,
        entity_type="modifier_group",
        entity_id=str(group.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"name": group.name, "brand_id": str(brand_id)},
    )

    await db.commit()
    await db.refresh(group)
    return group


async def update_modifier_group(
    db: AsyncSession,
    brand_id: uuid.UUID,
    group_id: uuid.UUID,
    payload: ModifierGroupUpdate,
    actor: POSUser,
) -> ModifierGroup:
    """Update a modifier group's mutable fields."""
    group = await _get_group_or_404(db, brand_id, group_id)
    before = {"name": group.name, "min_selections": group.min_selections, "max_selections": group.max_selections}

    if payload.name is not None:
        group.name = payload.name
    if payload.min_selections is not None:
        group.min_selections = payload.min_selections
    if payload.max_selections is not None:
        group.max_selections = payload.max_selections

    await log_action(
        db=db,
        action=MODIFIER_GROUP_UPDATED,
        entity_type="modifier_group",
        entity_id=str(group.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state={"name": group.name, "min_selections": group.min_selections, "max_selections": group.max_selections},
    )

    await db.commit()
    await db.refresh(group)
    return group


# ── Modifier option operations ────────────────────────────────────────────────


async def list_modifier_options(
    db: AsyncSession,
    brand_id: uuid.UUID,
    group_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
) -> list[ModifierOption]:
    """Return active options for a modifier group."""
    await _get_group_or_404(db, brand_id, group_id)

    result = await db.execute(
        select(ModifierOption)
        .where(
            ModifierOption.modifier_group_id == group_id,
            ModifierOption.is_active == True,  # noqa: E712
        )
        .order_by(ModifierOption.display_order, ModifierOption.name)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def create_modifier_option(
    db: AsyncSession,
    brand_id: uuid.UUID,
    group_id: uuid.UUID,
    payload: ModifierOptionCreate,
    actor: POSUser,
) -> ModifierOption:
    """Create a modifier option and write an audit row."""
    await _get_group_or_404(db, brand_id, group_id)

    option = ModifierOption(
        id=uuid.uuid4(),
        modifier_group_id=group_id,
        name=payload.name,
        price_delta_cents=payload.price_delta_cents,
        display_order=payload.display_order,
        is_active=True,
    )
    db.add(option)

    await log_action(
        db=db,
        action=MODIFIER_OPTION_CREATED,
        entity_type="modifier_option",
        entity_id=str(option.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "name": option.name,
            "price_delta_cents": option.price_delta_cents,
            "group_id": str(group_id),
        },
    )

    await db.commit()
    await db.refresh(option)
    return option


async def update_modifier_option(
    db: AsyncSession,
    brand_id: uuid.UUID,
    option_id: uuid.UUID,
    payload: ModifierOptionUpdate,
    actor: POSUser,
) -> ModifierOption:
    """Update a modifier option's mutable fields."""
    option = await _get_option_or_404(db, brand_id, option_id)
    before = {"name": option.name, "price_delta_cents": option.price_delta_cents}

    if payload.name is not None:
        option.name = payload.name
    if payload.price_delta_cents is not None:
        option.price_delta_cents = payload.price_delta_cents
    if payload.display_order is not None:
        option.display_order = payload.display_order

    await log_action(
        db=db,
        action=MODIFIER_OPTION_UPDATED,
        entity_type="modifier_option",
        entity_id=str(option.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state={"name": option.name, "price_delta_cents": option.price_delta_cents},
    )

    await db.commit()
    await db.refresh(option)
    return option


# ── Product–modifier link operations ──────────────────────────────────────────


async def link_modifier_group(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID,
    group_id: uuid.UUID,
    display_order: int,
    actor: POSUser,
) -> ProductModifierGroupLink:
    """
    Attach a modifier group to a product.

    Validates both product and group belong to the same brand.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        product_id: Product to attach the modifier to.
        group_id: Modifier group to attach.
        display_order: Order in which this group appears during order entry.
        actor: The authenticated POS user.

    Returns:
        ProductModifierGroupLink: The created link row.

    Raises:
        HTTPException: 404 if product or group not found.
        HTTPException: 409 if the link already exists.
    """
    product_result = await db.execute(
        select(Product).where(Product.id == product_id, Product.brand_id == brand_id)
    )
    if product_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    await _get_group_or_404(db, brand_id, group_id)

    existing_result = await db.execute(
        select(ProductModifierGroupLink).where(
            ProductModifierGroupLink.product_id == product_id,
            ProductModifierGroupLink.modifier_group_id == group_id,
        )
    )
    if existing_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This modifier group is already linked to the product",
        )

    link = ProductModifierGroupLink(
        id=uuid.uuid4(),
        product_id=product_id,
        modifier_group_id=group_id,
        display_order=display_order,
    )
    db.add(link)

    await log_action(
        db=db,
        action=PRODUCT_MODIFIER_LINKED,
        entity_type="product_modifier_group_link",
        entity_id=str(link.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"product_id": str(product_id), "modifier_group_id": str(group_id)},
    )

    await db.commit()
    await db.refresh(link)
    return link


async def unlink_modifier_group(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID,
    group_id: uuid.UUID,
    actor: POSUser,
) -> None:
    """Remove a modifier group link from a product."""
    result = await db.execute(
        select(ProductModifierGroupLink)
        .join(Product, ProductModifierGroupLink.product_id == Product.id)
        .where(
            ProductModifierGroupLink.product_id == product_id,
            ProductModifierGroupLink.modifier_group_id == group_id,
            Product.brand_id == brand_id,
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Modifier group link not found for this product",
        )

    await log_action(
        db=db,
        action=PRODUCT_MODIFIER_UNLINKED,
        entity_type="product_modifier_group_link",
        entity_id=str(link.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"product_id": str(product_id), "modifier_group_id": str(group_id)},
    )

    await db.delete(link)
    await db.commit()
