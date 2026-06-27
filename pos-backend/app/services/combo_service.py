"""Business logic for product combo groups and combo options.

Circular reference detection: before adding a product as a combo option, the
service performs a depth-first traversal of the combo graph starting from the
candidate product. If the traversal reaches the parent product, a 400 is raised.

Example of a circular reference:
  Product A "Meal" has combo group with option → Product B "Burger"
  Product B "Burger" has combo group with option → Product A "Meal"  ← circular
"""

import uuid
from collections import deque

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    COMBO_GROUP_CREATED,
    COMBO_OPTION_ADDED,
    COMBO_OPTION_REMOVED,
)
from app.constants.statuses import ActorType
from app.models.superadmin import SuperAdmin
from app.models.user import User
from app.models.product import Product
from app.models.product_combo_group import ProductComboGroup
from app.models.product_combo_option import ProductComboOption
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


# ── Inline schemas ─────────────────────────────────────────────────────────────

from pydantic import BaseModel, Field


class ComboGroupCreate(BaseModel):
    """Payload for creating a combo group."""

    name: str = Field(..., min_length=1, max_length=100)
    min_selections: int = Field(1, ge=0)
    max_selections: int = Field(1, ge=1)
    is_required: bool = True
    display_order: int = Field(0, ge=0)


class ComboGroupResponse(BaseModel):
    """Response schema for a combo group."""

    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    min_selections: int
    max_selections: int
    is_required: bool
    display_order: int

    model_config = {"from_attributes": True}


class ComboOptionCreate(BaseModel):
    """Payload for adding an option to a combo group."""

    product_id: uuid.UUID
    price_delta_cents: int = Field(0)
    display_order: int = Field(0, ge=0)


class ComboOptionResponse(BaseModel):
    """Response schema for a combo option."""

    id: uuid.UUID
    combo_group_id: uuid.UUID
    product_id: uuid.UUID
    price_delta_cents: int
    display_order: int

    model_config = {"from_attributes": True}


# ── Circular reference detection ──────────────────────────────────────────────


async def _collect_reachable_products(
    db: AsyncSession,
    start_product_id: uuid.UUID,
) -> set[uuid.UUID]:
    """
    BFS over the combo graph starting from start_product_id.

    Returns all product IDs reachable by following combo group options.
    Used to detect circular references before adding a new combo option.

    Args:
        db: Active database session.
        start_product_id: Root of the traversal.

    Returns:
        set[uuid.UUID]: All product IDs reachable from start_product_id.
    """
    visited: set[uuid.UUID] = set()
    queue: deque[uuid.UUID] = deque([start_product_id])

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        # Find all products reachable via combo options from current
        result = await db.execute(
            select(ProductComboOption.product_id)
            .join(ProductComboGroup, ProductComboOption.combo_group_id == ProductComboGroup.id)
            .where(ProductComboGroup.product_id == current)
        )
        for (reachable_id,) in result:
            if reachable_id not in visited:
                queue.append(reachable_id)

    return visited


async def _check_circular_reference(
    db: AsyncSession,
    parent_product_id: uuid.UUID,
    candidate_product_id: uuid.UUID,
) -> None:
    """
    Raise HTTP 400 if adding candidate as an option would create a circular combo chain.

    Args:
        db: Active database session.
        parent_product_id: The combo product being edited.
        candidate_product_id: The product proposed as a new option.

    Raises:
        HTTPException: 400 if adding the option would create a cycle.
    """
    # Direct self-reference check
    if candidate_product_id == parent_product_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A product cannot be a combo option of itself",
        )

    # Traverse the combo graph from the candidate — if we reach the parent, it's circular
    reachable = await _collect_reachable_products(db, candidate_product_id)
    if parent_product_id in reachable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Adding this option would create a circular combo reference",
        )


# ── Public service functions ───────────────────────────────────────────────────


async def list_combo_groups(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
) -> list[ProductComboGroup]:
    """
    Return combo groups for a product.

    Args:
        db: Active database session.
        brand_id: Brand scope for the product lookup.
        product_id: Product to list combo groups for.
        skip: Pagination offset.
        limit: Maximum rows to return.

    Returns:
        list[ProductComboGroup]: Combo groups ordered by display_order.

    Raises:
        HTTPException: 404 if the product is not found within the brand.
    """
    product_result = await db.execute(
        select(Product).where(Product.id == product_id, Product.brand_id == brand_id)
    )
    if product_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    result = await db.execute(
        select(ProductComboGroup)
        .where(ProductComboGroup.product_id == product_id)
        .order_by(ProductComboGroup.display_order)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def create_combo_group(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: ComboGroupCreate,
    actor: User | SuperAdmin,
) -> ProductComboGroup:
    """
    Create a combo group for a product.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        product_id: Product to attach the group to.
        payload: Group creation data.
        actor: The authenticated POS user.

    Returns:
        ProductComboGroup: The newly created group.

    Raises:
        HTTPException: 404 if the product is not found within the brand.
    """
    product_result = await db.execute(
        select(Product).where(Product.id == product_id, Product.brand_id == brand_id)
    )
    if product_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    group = ProductComboGroup(
        id=uuid.uuid4(),
        product_id=product_id,
        name=payload.name,
        min_selections=payload.min_selections,
        max_selections=payload.max_selections,
        is_required=payload.is_required,
        display_order=payload.display_order,
    )
    db.add(group)

    await log_action(
        db=db,
        action=COMBO_GROUP_CREATED,
        entity_type="product_combo_group",
        entity_id=str(group.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"product_id": str(product_id), "name": group.name},
    )

    await db.commit()
    await db.refresh(group)
    log.info("combo_group.created", group_id=str(group.id), product_id=str(product_id))
    return group


async def list_combo_options(
    db: AsyncSession,
    combo_group_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
) -> list[ProductComboOption]:
    """Return options for a combo group ordered by display_order."""
    result = await db.execute(
        select(ProductComboOption)
        .where(ProductComboOption.combo_group_id == combo_group_id)
        .order_by(ProductComboOption.display_order)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def add_combo_option(
    db: AsyncSession,
    brand_id: uuid.UUID,
    combo_group_id: uuid.UUID,
    payload: ComboOptionCreate,
    actor: User | SuperAdmin,
) -> ProductComboOption:
    """
    Add a product as an option to a combo group.

    Performs a circular reference check before inserting. Validates that the
    candidate product belongs to the same brand as the parent combo product.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        combo_group_id: The combo group to add the option to.
        payload: Option data (product_id, price_delta_cents).
        actor: The authenticated POS user.

    Returns:
        ProductComboOption: The created option row.

    Raises:
        HTTPException: 404 if the group or candidate product not found in brand.
        HTTPException: 400 if adding the option would create a circular reference.
        HTTPException: 409 if the product is already an option in this group.
    """
    # Load the combo group to get the parent product_id for cycle detection
    group_result = await db.execute(
        select(ProductComboGroup).where(ProductComboGroup.id == combo_group_id)
    )
    group = group_result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Combo group not found")

    # Validate parent product belongs to this brand
    parent_result = await db.execute(
        select(Product).where(Product.id == group.product_id, Product.brand_id == brand_id)
    )
    if parent_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Combo group not found")

    # Validate candidate product belongs to this brand
    candidate_result = await db.execute(
        select(Product).where(Product.id == payload.product_id, Product.brand_id == brand_id)
    )
    if candidate_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate product not found within this brand",
        )

    # Circular reference check — raises 400 if cycle detected
    await _check_circular_reference(db, group.product_id, payload.product_id)

    # Prevent duplicate option in same group
    existing_result = await db.execute(
        select(ProductComboOption).where(
            ProductComboOption.combo_group_id == combo_group_id,
            ProductComboOption.product_id == payload.product_id,
        )
    )
    if existing_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This product is already an option in this combo group",
        )

    option = ProductComboOption(
        id=uuid.uuid4(),
        combo_group_id=combo_group_id,
        product_id=payload.product_id,
        price_delta_cents=payload.price_delta_cents,
        display_order=payload.display_order,
    )
    db.add(option)

    await log_action(
        db=db,
        action=COMBO_OPTION_ADDED,
        entity_type="product_combo_option",
        entity_id=str(option.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "combo_group_id": str(combo_group_id),
            "product_id": str(payload.product_id),
            "price_delta_cents": payload.price_delta_cents,
        },
    )

    await db.commit()
    await db.refresh(option)
    log.info("combo_option.added", option_id=str(option.id), group_id=str(combo_group_id))
    return option


async def remove_combo_option(
    db: AsyncSession,
    brand_id: uuid.UUID,
    option_id: uuid.UUID,
    actor: User | SuperAdmin,
) -> None:
    """
    Remove a combo option.

    Args:
        db: Active database session.
        brand_id: Brand scope — validates via the parent combo group's product.
        option_id: UUID of the option to remove.
        actor: The authenticated POS user.

    Raises:
        HTTPException: 404 if the option is not found within the brand.
    """
    result = await db.execute(
        select(ProductComboOption)
        .join(ProductComboGroup, ProductComboOption.combo_group_id == ProductComboGroup.id)
        .join(Product, ProductComboGroup.product_id == Product.id)
        .where(ProductComboOption.id == option_id, Product.brand_id == brand_id)
    )
    option = result.scalar_one_or_none()
    if option is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Combo option not found"
        )

    await log_action(
        db=db,
        action=COMBO_OPTION_REMOVED,
        entity_type="product_combo_option",
        entity_id=str(option.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={
            "combo_group_id": str(option.combo_group_id),
            "product_id": str(option.product_id),
        },
    )

    await db.delete(option)
    await db.commit()
    log.info("combo_option.removed", option_id=str(option_id))
