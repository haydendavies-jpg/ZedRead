"""Business logic for Category CRUD operations.

Every category must belong to a Reporting Group (Stage 16, brand-scoped, one
level above Category). create_category() auto-assigns the brand's default
reporting group when the caller omits reporting_group_id, so the API
guarantees the column is never left unset even though the portal always
prompts for one.
"""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import CATEGORY_CREATED, CATEGORY_UPDATED
from app.models.category import Category
from app.models.reporting_group import ReportingGroup
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryUpdate
from app.services.audit_service import log_action
from app.services.reporting_group_service import get_default_reporting_group

log = structlog.get_logger(__name__)


async def _validate_reporting_group(
    db: AsyncSession, brand_id: uuid.UUID, reporting_group_id: uuid.UUID
) -> None:
    """
    Raise HTTP 400 if the reporting group does not belong to the given brand.

    Args:
        db: Active database session.
        brand_id: Expected brand owner of the reporting group.
        reporting_group_id: UUID of the reporting group to validate.

    Raises:
        HTTPException: 404 if the reporting group does not exist.
        HTTPException: 400 if the reporting group belongs to a different brand.
    """
    result = await db.execute(select(ReportingGroup).where(ReportingGroup.id == reporting_group_id))
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reporting group not found")
    if group.brand_id != brand_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reporting group belongs to a different brand",
        )


async def list_categories(
    db: AsyncSession,
    brand_id: uuid.UUID,
    skip: int = 0,
    limit: int = 200,
    include_inactive: bool = False,
) -> list[Category]:
    """
    List categories for a brand, paginated.

    Args:
        db: Active database session.
        brand_id: UUID of the brand to list categories for.
        skip: Pagination offset.
        limit: Maximum number of categories to return.
        include_inactive: When True, also return soft-deleted categories (Stage 20
            table view filters active/inactive client-side rather than via a repeat API call).

    Returns:
        list[Category]: Categories ordered by display_order.
    """
    query = (
        select(Category)
        .where(Category.brand_id == brand_id)
        .order_by(Category.display_order, Category.name)
        .offset(skip)
        .limit(limit)
    )
    if not include_inactive:
        query = query.where(Category.is_active == True)  # noqa: E712
    result = await db.execute(query)
    return list(result.scalars().all())


async def create_category(
    db: AsyncSession,
    brand_id: uuid.UUID,
    payload: CategoryCreate,
    actor: User,
    import_id: uuid.UUID | None = None,
) -> Category:
    """
    Create a new product category, auto-assigning the brand's default reporting group if omitted.

    Args:
        db: Active database session.
        brand_id: UUID of the brand to create the category under.
        payload: Category creation data.
        actor: The authenticated user performing the action (for audit logging).
        import_id: Batch ID shared by every row of a bulk import (Stage 19) so
            the audit trail can trace a whole upload; None for direct API calls.

    Returns:
        Category: The created category.

    Raises:
        HTTPException: 404/400 if an explicit reporting_group_id is invalid for this brand.
    """
    if payload.reporting_group_id is not None:
        await _validate_reporting_group(db, brand_id, payload.reporting_group_id)
        reporting_group_id = payload.reporting_group_id
    else:
        default_group = await get_default_reporting_group(db, brand_id)
        reporting_group_id = default_group.id

    cat = Category(
        id=uuid.uuid4(),
        brand_id=brand_id,
        reporting_group_id=reporting_group_id,
        name=payload.name,
        display_order=payload.display_order,
        default_color=payload.default_color,
        is_system=False,
        is_active=True,
    )
    db.add(cat)
    after_state: dict = {"name": payload.name, "reporting_group_id": str(reporting_group_id)}
    if import_id is not None:
        after_state["import_id"] = str(import_id)
    await log_action(
        db=db,
        action=CATEGORY_CREATED,
        entity_type="category",
        entity_id=str(cat.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state=after_state,
    )
    await db.commit()
    await db.refresh(cat)
    return cat


async def update_category(
    db: AsyncSession,
    brand_id: uuid.UUID,
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    actor: User,
    import_id: uuid.UUID | None = None,
) -> Category:
    """
    Update a category's mutable fields. System categories cannot be renamed or deactivated.

    Args:
        db: Active database session.
        brand_id: UUID of the brand the category belongs to.
        category_id: UUID of the category to update.
        payload: Fields to update.
        actor: The authenticated user performing the action (for audit logging).
        import_id: Batch ID shared by every row of a bulk import (Stage 19) so
            the audit trail can trace a whole upload; None for direct API calls.

    Returns:
        Category: The updated category.

    Raises:
        HTTPException: 404 if the category does not exist for this brand.
        HTTPException: 403 if a system category is renamed/deactivated.
        HTTPException: 404/400 if a new reporting_group_id is invalid for this brand.
    """
    result = await db.execute(select(Category).where(Category.id == category_id, Category.brand_id == brand_id))
    cat = result.scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    if cat.is_system and (payload.name is not None or payload.is_active is False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System categories cannot be renamed or deactivated",
        )

    before: dict = {}
    after: dict = {}
    if payload.name is not None:
        before["name"] = cat.name
        cat.name = payload.name
        after["name"] = payload.name
    if payload.reporting_group_id is not None:
        await _validate_reporting_group(db, brand_id, payload.reporting_group_id)
        before["reporting_group_id"] = str(cat.reporting_group_id)
        cat.reporting_group_id = payload.reporting_group_id
        after["reporting_group_id"] = str(payload.reporting_group_id)
    if payload.display_order is not None:
        before["display_order"] = cat.display_order
        cat.display_order = payload.display_order
        after["display_order"] = payload.display_order
    if payload.is_active is not None:
        before["is_active"] = cat.is_active
        cat.is_active = payload.is_active
        after["is_active"] = payload.is_active
    if payload.default_color is not None:
        before["default_color"] = cat.default_color
        cat.default_color = payload.default_color
        after["default_color"] = payload.default_color

    if import_id is not None:
        after["import_id"] = str(import_id)

    await log_action(
        db=db,
        action=CATEGORY_UPDATED,
        entity_type="category",
        entity_id=str(cat.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after,
    )
    await db.commit()
    await db.refresh(cat)
    return cat
