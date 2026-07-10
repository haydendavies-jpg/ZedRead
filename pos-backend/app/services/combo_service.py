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
    COMBO_GROUP_DEACTIVATED,
    COMBO_GROUP_REACTIVATED,
    COMBO_GROUP_UPDATED,
    COMBO_OPTION_ADDED,
    COMBO_OPTION_REMOVED,
)
from app.constants.statuses import ActorType
from app.models.superadmin import SuperAdmin
from app.models.user import User
from app.models.product import Product
from app.models.product_combo_group import ProductComboGroup
from app.models.product_combo_option import ProductComboOption
from app.schemas.combo import (
    ComboGroupCreate,
    ComboGroupResponse,
    ComboGroupUpdate,
    ComboOptionCreate,
    ComboOptionResponse,
)
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


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


async def _get_combo_group_or_404(
    db: AsyncSession, brand_id: uuid.UUID, group_id: uuid.UUID
) -> ProductComboGroup:
    """
    Fetch a ProductComboGroup scoped to a brand via its parent product, or raise HTTP 404.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        group_id: UUID of the combo group.

    Returns:
        ProductComboGroup: The found instance.

    Raises:
        HTTPException: 404 if not found.
    """
    result = await db.execute(
        select(ProductComboGroup)
        .join(Product, ProductComboGroup.product_id == Product.id)
        .where(ProductComboGroup.id == group_id, Product.brand_id == brand_id)
    )
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Combo group not found")
    return group


async def list_combo_groups(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
) -> list[ProductComboGroup]:
    """
    Return active combo groups for a product.

    Args:
        db: Active database session.
        brand_id: Brand scope for the product lookup.
        product_id: Product to list combo groups for.
        skip: Pagination offset.
        limit: Maximum rows to return.

    Returns:
        list[ProductComboGroup]: Active combo groups ordered by display_order.

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
        .where(
            ProductComboGroup.product_id == product_id,
            ProductComboGroup.is_active == True,  # noqa: E712
        )
        .order_by(ProductComboGroup.display_order)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_combo_groups_for_brand(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID | None = None,
    include_inactive: bool = False,
    skip: int = 0,
    limit: int = 200,
) -> list[tuple[ProductComboGroup, str, str]]:
    """
    Return every combo group across the brand's catalog, joined to its parent product.

    Powers the Stage 22 combined Variants+Combos portal page, which lists
    combo groups across all products rather than one product at a time.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        product_id: Optional filter — only combo groups of this product.
        include_inactive: When True, also return soft-deleted combo groups.
        skip: Pagination offset.
        limit: Maximum rows to return.

    Returns:
        list[tuple[ProductComboGroup, str, str]]: Each tuple is
            (group, product_name, product_ref), ordered by product name.
    """
    query = (
        select(ProductComboGroup, Product.name, Product.ref)
        .join(Product, ProductComboGroup.product_id == Product.id)
        .where(Product.brand_id == brand_id)
        .order_by(Product.name, ProductComboGroup.display_order)
        .offset(skip)
        .limit(limit)
    )
    if not include_inactive:
        query = query.where(ProductComboGroup.is_active == True)  # noqa: E712
    if product_id is not None:
        query = query.where(ProductComboGroup.product_id == product_id)

    result = await db.execute(query)
    return [tuple(row) for row in result.all()]


async def create_combo_group(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: ComboGroupCreate,
    actor: User | SuperAdmin,
    import_id: uuid.UUID | None = None,
) -> ProductComboGroup:
    """
    Create a combo group for a product.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        product_id: Product to attach the group to.
        payload: Group creation data.
        actor: The authenticated POS user.
        import_id: Batch ID shared by every row of a bulk import; None for direct calls.

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
        display_name=payload.display_name,
        min_selections=payload.min_selections,
        max_selections=payload.max_selections,
        is_required=payload.is_required,
        display_order=payload.display_order,
        is_active=True,
    )
    db.add(group)
    await db.flush()

    after_state: dict = {"product_id": str(product_id), "name": group.name}
    if import_id is not None:
        after_state["import_id"] = str(import_id)

    await log_action(
        db=db,
        action=COMBO_GROUP_CREATED,
        entity_type="product_combo_group",
        entity_id=str(group.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state=after_state,
    )

    await db.commit()
    await db.refresh(group)
    log.info("combo_group.created", group_id=str(group.id), product_id=str(product_id))
    return group


async def update_combo_group(
    db: AsyncSession,
    brand_id: uuid.UUID,
    group_id: uuid.UUID,
    payload: ComboGroupUpdate,
    actor: User | SuperAdmin,
    import_id: uuid.UUID | None = None,
) -> ProductComboGroup:
    """
    Update a combo group's mutable fields.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        group_id: UUID of the combo group to update.
        payload: Fields to update.
        actor: The authenticated user performing the action.
        import_id: Batch ID shared by every row of a bulk import; None for direct calls.

    Returns:
        ProductComboGroup: The updated combo group.

    Raises:
        HTTPException: 404 if not found.
    """
    group = await _get_combo_group_or_404(db, brand_id, group_id)
    before: dict = {}

    for field in ("name", "display_name", "min_selections", "max_selections", "is_required", "display_order"):
        value = getattr(payload, field)
        if value is not None:
            before[field] = getattr(group, field)
            setattr(group, field, value)

    after_state = payload.model_dump(exclude_none=True)
    if import_id is not None:
        after_state["import_id"] = str(import_id)

    await log_action(
        db=db,
        action=COMBO_GROUP_UPDATED,
        entity_type="product_combo_group",
        entity_id=str(group.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after_state,
    )

    await db.commit()
    await db.refresh(group)
    return group


async def deactivate_combo_group(
    db: AsyncSession,
    brand_id: uuid.UUID,
    group_id: uuid.UUID,
    actor: User | SuperAdmin,
) -> ProductComboGroup:
    """
    Soft-delete a combo group (set is_active=False).

    Args:
        db: Active database session.
        brand_id: Brand scope.
        group_id: UUID of the combo group to deactivate.
        actor: The authenticated user performing the action.

    Returns:
        ProductComboGroup: The deactivated combo group.

    Raises:
        HTTPException: 404 if not found.
        HTTPException: 409 if already inactive.
    """
    group = await _get_combo_group_or_404(db, brand_id, group_id)

    if not group.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Combo group is already inactive",
        )

    group.is_active = False

    await log_action(
        db=db,
        action=COMBO_GROUP_DEACTIVATED,
        entity_type="product_combo_group",
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


async def set_combo_group_active_state(
    db: AsyncSession,
    brand_id: uuid.UUID,
    group_id: uuid.UUID,
    is_active: bool,
    actor: User | SuperAdmin,
    import_id: uuid.UUID | None = None,
) -> ProductComboGroup:
    """
    Set a combo group's is_active flag directly (activate or soft-delete), idempotently.

    Unlike deactivate_combo_group(), setting the flag to its current value is a
    silent no-op rather than a 409 — same convention as
    product_service.set_product_active_state(). Used by import_service.py and
    the portal's POST /combos/{id}/activate route.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        group_id: UUID of the combo group to update.
        is_active: The desired active state.
        actor: The authenticated user performing the action.
        import_id: Batch ID shared by every row of a bulk import; None for direct calls.

    Returns:
        ProductComboGroup: The combo group, with is_active set to the requested value.

    Raises:
        HTTPException: 404 if not found.
    """
    group = await _get_combo_group_or_404(db, brand_id, group_id)
    if group.is_active == is_active:
        return group

    group.is_active = is_active

    after_state: dict = {"is_active": is_active}
    if import_id is not None:
        after_state["import_id"] = str(import_id)

    await log_action(
        db=db,
        action=COMBO_GROUP_REACTIVATED if is_active else COMBO_GROUP_DEACTIVATED,
        entity_type="product_combo_group",
        entity_id=str(group.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": not is_active},
        after_state=after_state,
    )

    await db.commit()
    await db.refresh(group)
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
