"""Business logic for modifier groups, modifier options, and product-modifier links."""

import uuid
from collections import defaultdict

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    MODIFIER_GROUP_CREATED,
    MODIFIER_GROUP_DEACTIVATED,
    MODIFIER_GROUP_DUPLICATED,
    MODIFIER_GROUP_UPDATED,
    MODIFIER_OPTION_CREATED,
    MODIFIER_OPTION_DEACTIVATED,
    MODIFIER_OPTION_GROUP_LINKED,
    MODIFIER_OPTION_GROUP_UNLINKED,
    MODIFIER_OPTION_UPDATED,
    PRODUCT_MODIFIER_LINKED,
    PRODUCT_MODIFIER_UNLINKED,
)
from app.constants.statuses import ActorType
from app.models.modifier_group import ModifierGroup
from app.models.modifier_option import ModifierOption
from app.models.modifier_option_group_link import ModifierOptionGroupLink
from app.models.superadmin import SuperAdmin
from app.models.user import User
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


class ModifierOptionLinkCreate(BaseModel):
    """Payload for linking an option to another modifier group it expands into ("comboing")."""

    linked_group_id: uuid.UUID
    display_order: int = Field(0, ge=0)


class LinkedGroupOptionOut(BaseModel):
    """One option belonging to a linked (combo) group — flat, no further nesting."""

    id: uuid.UUID
    name: str
    price_delta_cents: int


class LinkedGroupOut(BaseModel):
    """A modifier group linked from an option, with its own active options."""

    id: uuid.UUID
    name: str
    min_selections: int
    max_selections: int
    options: list[LinkedGroupOptionOut]


class ModifierOptionDetail(ModifierOptionResponse):
    """An option plus the groups it links to ("comboing") — used by the detailed group view."""

    linked_groups: list[LinkedGroupOut] = []


class ModifierGroupDetail(ModifierGroupResponse):
    """A modifier group with its active options (each carrying its own links) and usage count."""

    options: list[ModifierOptionDetail]
    used_by_count: int


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
    actor: User | SuperAdmin,
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
    actor: User | SuperAdmin,
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
    actor: User | SuperAdmin,
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
    actor: User | SuperAdmin,
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
    actor: User | SuperAdmin,
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
    actor: User | SuperAdmin,
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


# ── Deactivation / duplication ────────────────────────────────────────────────


async def deactivate_modifier_group(
    db: AsyncSession, brand_id: uuid.UUID, group_id: uuid.UUID, actor: User | SuperAdmin
) -> ModifierGroup:
    """Soft-delete a modifier group (excluded from the POS and the Modifiers tab)."""
    group = await _get_group_or_404(db, brand_id, group_id)
    group.is_active = False

    await log_action(
        db=db,
        action=MODIFIER_GROUP_DEACTIVATED,
        entity_type="modifier_group",
        entity_id=str(group.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": True},
        after_state={"is_active": False},
    )

    await db.commit()
    await db.refresh(group)
    return group


async def deactivate_modifier_option(
    db: AsyncSession, brand_id: uuid.UUID, option_id: uuid.UUID, actor: User | SuperAdmin
) -> ModifierOption:
    """Soft-delete a modifier option."""
    option = await _get_option_or_404(db, brand_id, option_id)
    option.is_active = False

    await log_action(
        db=db,
        action=MODIFIER_OPTION_DEACTIVATED,
        entity_type="modifier_option",
        entity_id=str(option.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": True},
        after_state={"is_active": False},
    )

    await db.commit()
    await db.refresh(option)
    return option


async def duplicate_modifier_group(
    db: AsyncSession, brand_id: uuid.UUID, group_id: uuid.UUID, actor: User | SuperAdmin
) -> ModifierGroup:
    """
    Duplicate a modifier group and its active options (name suffixed "(copy)").

    Comboing links on the source options are not copied — a duplicated option
    starts with no linked groups so the operator chooses fresh links.
    """
    source = await _get_group_or_404(db, brand_id, group_id)
    options_result = await db.execute(
        select(ModifierOption)
        .where(ModifierOption.modifier_group_id == group_id, ModifierOption.is_active == True)  # noqa: E712
        .order_by(ModifierOption.display_order, ModifierOption.name)
    )

    new_group = ModifierGroup(
        id=uuid.uuid4(),
        brand_id=brand_id,
        name=f"{source.name} (copy)",
        min_selections=source.min_selections,
        max_selections=source.max_selections,
        is_active=True,
    )
    db.add(new_group)

    for option in options_result.scalars().all():
        db.add(
            ModifierOption(
                id=uuid.uuid4(),
                modifier_group_id=new_group.id,
                name=option.name,
                price_delta_cents=option.price_delta_cents,
                display_order=option.display_order,
                is_active=True,
            )
        )

    await log_action(
        db=db,
        action=MODIFIER_GROUP_DUPLICATED,
        entity_type="modifier_group",
        entity_id=str(new_group.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"name": new_group.name, "duplicated_from": str(source.id)},
    )

    await db.commit()
    await db.refresh(new_group)
    return new_group


# ── Comboing — option → linked group ──────────────────────────────────────────


async def link_option_group(
    db: AsyncSession,
    brand_id: uuid.UUID,
    option_id: uuid.UUID,
    payload: ModifierOptionLinkCreate,
    actor: User | SuperAdmin,
) -> ModifierOptionGroupLink:
    """
    Link a modifier option to another modifier group it expands into ("comboing").

    Args:
        db: Active database session.
        brand_id: Brand scope.
        option_id: The option that will surface the linked group.
        payload: Which group to link and its display order.
        actor: The authenticated user performing the action.

    Returns:
        ModifierOptionGroupLink: The created link row.

    Raises:
        HTTPException: 404 if the option or linked group is not found for this brand.
        HTTPException: 400 if an option is linked to its own parent group.
        HTTPException: 409 if the link already exists.
    """
    option = await _get_option_or_404(db, brand_id, option_id)
    linked_group = await _get_group_or_404(db, brand_id, payload.linked_group_id)

    if linked_group.id == option.modifier_group_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An option cannot link to the group it belongs to",
        )

    existing_result = await db.execute(
        select(ModifierOptionGroupLink).where(
            ModifierOptionGroupLink.modifier_option_id == option_id,
            ModifierOptionGroupLink.linked_group_id == payload.linked_group_id,
        )
    )
    if existing_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This group is already linked")

    link = ModifierOptionGroupLink(
        id=uuid.uuid4(),
        modifier_option_id=option_id,
        linked_group_id=payload.linked_group_id,
        display_order=payload.display_order,
    )
    db.add(link)

    await log_action(
        db=db,
        action=MODIFIER_OPTION_GROUP_LINKED,
        entity_type="modifier_option_group_link",
        entity_id=str(link.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"modifier_option_id": str(option_id), "linked_group_id": str(payload.linked_group_id)},
    )

    await db.commit()
    await db.refresh(link)
    return link


async def unlink_option_group(
    db: AsyncSession,
    brand_id: uuid.UUID,
    option_id: uuid.UUID,
    linked_group_id: uuid.UUID,
    actor: User | SuperAdmin,
) -> None:
    """Remove a comboing link between an option and a linked group."""
    await _get_option_or_404(db, brand_id, option_id)

    result = await db.execute(
        select(ModifierOptionGroupLink).where(
            ModifierOptionGroupLink.modifier_option_id == option_id,
            ModifierOptionGroupLink.linked_group_id == linked_group_id,
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    await log_action(
        db=db,
        action=MODIFIER_OPTION_GROUP_UNLINKED,
        entity_type="modifier_option_group_link",
        entity_id=str(link.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"modifier_option_id": str(option_id), "linked_group_id": str(linked_group_id)},
    )

    await db.delete(link)
    await db.commit()


# ── Detailed (nested) listing for the Modifiers tab ───────────────────────────


async def _active_options_by_group(
    db: AsyncSession, group_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[ModifierOption]]:
    """Fetch active options for a set of groups in one query, keyed by modifier_group_id."""
    if not group_ids:
        return {}
    result = await db.execute(
        select(ModifierOption)
        .where(ModifierOption.modifier_group_id.in_(group_ids), ModifierOption.is_active == True)  # noqa: E712
        .order_by(ModifierOption.display_order, ModifierOption.name)
    )
    by_group: dict[uuid.UUID, list[ModifierOption]] = defaultdict(list)
    for option in result.scalars().all():
        by_group[option.modifier_group_id].append(option)
    return by_group


async def list_modifier_groups_detailed(
    db: AsyncSession,
    brand_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
) -> list[ModifierGroupDetail]:
    """
    Return active modifier groups for a brand with their options (and each
    option's comboing links) and used-by-product count, nested — one call for
    the portal's Modifiers tab instead of one round trip per group.

    Batches every level (groups, their options, comboing links, and linked
    groups' own options) into a fixed number of queries regardless of catalog
    size — a per-group/per-option loop of individual queries here previously
    made this endpoint's cost scale with the number of options, which made
    every edit (each of which re-fetches this list) visibly slow on a
    non-trivial catalog.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        skip: Pagination offset.
        limit: Maximum groups to return.

    Returns:
        list[ModifierGroupDetail]: Active modifier groups, fully nested.
    """
    groups = await list_modifier_groups(db, brand_id, skip, limit)
    if not groups:
        return []
    group_ids = [g.id for g in groups]

    usage_result = await db.execute(
        select(ProductModifierGroupLink.modifier_group_id, func.count(func.distinct(ProductModifierGroupLink.product_id)))
        .join(ModifierGroup, ProductModifierGroupLink.modifier_group_id == ModifierGroup.id)
        .where(ModifierGroup.brand_id == brand_id)
        .group_by(ProductModifierGroupLink.modifier_group_id)
    )
    usage_by_group = dict(usage_result.all())

    options_by_group = await _active_options_by_group(db, group_ids)
    option_ids = [o.id for options in options_by_group.values() for o in options]

    links_by_option: dict[uuid.UUID, list[ModifierGroup]] = defaultdict(list)
    if option_ids:
        links_result = await db.execute(
            select(ModifierOptionGroupLink.modifier_option_id, ModifierGroup)
            .join(ModifierGroup, ModifierOptionGroupLink.linked_group_id == ModifierGroup.id)
            .where(ModifierOptionGroupLink.modifier_option_id.in_(option_ids))
            .order_by(ModifierOptionGroupLink.display_order)
        )
        for option_id, linked_group in links_result.all():
            links_by_option[option_id].append(linked_group)

    linked_group_ids = list({lg.id for groups_ in links_by_option.values() for lg in groups_})
    linked_group_options = await _active_options_by_group(db, linked_group_ids)

    detailed: list[ModifierGroupDetail] = []
    for group in groups:
        option_details = []
        for option in options_by_group.get(group.id, []):
            linked_groups = [
                LinkedGroupOut(
                    id=lg.id,
                    name=lg.name,
                    min_selections=lg.min_selections,
                    max_selections=lg.max_selections,
                    options=[
                        LinkedGroupOptionOut(id=o.id, name=o.name, price_delta_cents=o.price_delta_cents)
                        for o in linked_group_options.get(lg.id, [])
                    ],
                )
                for lg in links_by_option.get(option.id, [])
            ]
            option_details.append(
                ModifierOptionDetail(
                    id=option.id,
                    modifier_group_id=option.modifier_group_id,
                    name=option.name,
                    price_delta_cents=option.price_delta_cents,
                    display_order=option.display_order,
                    is_active=option.is_active,
                    linked_groups=linked_groups,
                )
            )

        detailed.append(
            ModifierGroupDetail(
                id=group.id,
                brand_id=group.brand_id,
                name=group.name,
                min_selections=group.min_selections,
                max_selections=group.max_selections,
                is_active=group.is_active,
                options=option_details,
                used_by_count=usage_by_group.get(group.id, 0),
            )
        )
    return detailed
