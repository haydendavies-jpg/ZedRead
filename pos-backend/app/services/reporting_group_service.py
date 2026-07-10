"""Business logic for Reporting Group CRUD operations (Stage 16).

Reporting Groups sit one level above Categories (brand-scoped). Every brand
has exactly one system default group, seeded alongside its 'Uncategorised'
category in brand_service.create_brand(); every Category must reference a
Reporting Group, falling back to the brand's default when none is supplied.
"""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    REPORTING_GROUP_CREATED,
    REPORTING_GROUP_DELETED,
    REPORTING_GROUP_UPDATED,
)
from app.models.category import Category
from app.models.reporting_group import ReportingGroup
from app.models.superadmin import SuperAdmin
from app.models.user import User
from app.schemas.reporting_group import ReportingGroupCreate, ReportingGroupUpdate
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


async def get_default_reporting_group(db: AsyncSession, brand_id: uuid.UUID) -> ReportingGroup:
    """
    Fetch a brand's system default reporting group.

    Every brand is guaranteed exactly one by brand_service.create_brand()
    (or the Stage 16 migration backfill for pre-existing brands).

    Args:
        db: Active database session.
        brand_id: UUID of the brand to fetch the default group for.

    Returns:
        ReportingGroup: The brand's default reporting group.

    Raises:
        HTTPException: 500 if the brand is somehow missing its default group.
    """
    result = await db.execute(
        select(ReportingGroup).where(
            ReportingGroup.brand_id == brand_id,
            ReportingGroup.is_default == True,  # noqa: E712
        )
    )
    default_group = result.scalar_one_or_none()
    if default_group is None:
        log.error("reporting_group.default_missing", brand_id=str(brand_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Brand is missing its default reporting group",
        )
    return default_group


async def _get_or_404(db: AsyncSession, reporting_group_id: uuid.UUID, brand_id: uuid.UUID) -> ReportingGroup:
    """
    Fetch a ReportingGroup by id scoped to a brand, or raise HTTP 404.

    Args:
        db: Active database session.
        reporting_group_id: UUID of the reporting group to fetch.
        brand_id: The brand the group must belong to.

    Returns:
        ReportingGroup: The found reporting group.

    Raises:
        HTTPException: 404 if no reporting group with this id exists for this brand.
    """
    result = await db.execute(
        select(ReportingGroup).where(
            ReportingGroup.id == reporting_group_id,
            ReportingGroup.brand_id == brand_id,
        )
    )
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reporting group not found")
    return group


async def list_reporting_groups(
    db: AsyncSession,
    brand_id: uuid.UUID,
    skip: int = 0,
    limit: int = 200,
) -> list[ReportingGroup]:
    """
    List reporting groups for a brand, paginated.

    Args:
        db: Active database session.
        brand_id: UUID of the brand to list reporting groups for.
        skip: Pagination offset.
        limit: Maximum number of reporting groups to return.

    Returns:
        list[ReportingGroup]: Reporting groups ordered by name (default group first).
    """
    result = await db.execute(
        select(ReportingGroup)
        .where(ReportingGroup.brand_id == brand_id)
        .order_by(ReportingGroup.is_default.desc(), ReportingGroup.name)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def create_reporting_group(
    db: AsyncSession,
    brand_id: uuid.UUID,
    payload: ReportingGroupCreate,
    actor: User | SuperAdmin,
    import_id: uuid.UUID | None = None,
) -> ReportingGroup:
    """
    Create a new (non-default, non-system) reporting group for a brand.

    Args:
        db: Active database session.
        brand_id: UUID of the brand to create the reporting group under.
        payload: Reporting group creation data.
        actor: The authenticated user performing the action (for audit logging).
        import_id: Batch ID shared by every row of a bulk import (Stage 19) so
            the audit trail can trace a whole upload; None for direct API calls.

    Returns:
        ReportingGroup: The created reporting group.
    """
    group = ReportingGroup(
        id=uuid.uuid4(),
        brand_id=brand_id,
        name=payload.name,
        is_default=False,
        is_system=False,
    )
    db.add(group)
    await db.flush()

    after_state: dict = {"name": group.name, "brand_id": str(brand_id)}
    if import_id is not None:
        after_state["import_id"] = str(import_id)

    await log_action(
        db=db,
        action=REPORTING_GROUP_CREATED,
        entity_type="reporting_group",
        entity_id=str(group.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state=after_state,
    )
    await db.commit()
    await db.refresh(group)
    log.info("reporting_group.created", reporting_group_id=str(group.id), brand_id=str(brand_id))
    return group


async def update_reporting_group(
    db: AsyncSession,
    brand_id: uuid.UUID,
    reporting_group_id: uuid.UUID,
    payload: ReportingGroupUpdate,
    actor: User | SuperAdmin,
    import_id: uuid.UUID | None = None,
) -> ReportingGroup:
    """
    Rename a reporting group. The system default group cannot be renamed.

    Args:
        db: Active database session.
        brand_id: UUID of the brand the reporting group belongs to.
        reporting_group_id: UUID of the reporting group to update.
        payload: Fields to update.
        actor: The authenticated user performing the action (for audit logging).
        import_id: Batch ID shared by every row of a bulk import (Stage 19) so
            the audit trail can trace a whole upload; None for direct API calls.

    Returns:
        ReportingGroup: The updated reporting group.

    Raises:
        HTTPException: 404 if not found; 403 if the group is system-protected.
    """
    group = await _get_or_404(db, reporting_group_id, brand_id)

    if group.is_system and payload.name is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The default reporting group cannot be renamed",
        )

    before: dict = {}
    if payload.name is not None:
        before["name"] = group.name
        group.name = payload.name

    after_state = payload.model_dump(exclude_none=True)
    if import_id is not None:
        after_state["import_id"] = str(import_id)

    await log_action(
        db=db,
        action=REPORTING_GROUP_UPDATED,
        entity_type="reporting_group",
        entity_id=str(group.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after_state,
    )
    await db.commit()
    await db.refresh(group)
    return group


async def delete_reporting_group(
    db: AsyncSession,
    brand_id: uuid.UUID,
    reporting_group_id: uuid.UUID,
    actor: User | SuperAdmin,
) -> None:
    """
    Delete a reporting group. Blocked for the default group or one still in use.

    Args:
        db: Active database session.
        brand_id: UUID of the brand the reporting group belongs to.
        reporting_group_id: UUID of the reporting group to delete.
        actor: The authenticated user performing the action (for audit logging).

    Raises:
        HTTPException: 404 if not found.
        HTTPException: 403 if the group is the brand's default.
        HTTPException: 409 if categories still reference this group.
    """
    group = await _get_or_404(db, reporting_group_id, brand_id)

    if group.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The default reporting group cannot be deleted",
        )

    in_use_result = await db.execute(
        select(func.count()).select_from(Category).where(Category.reporting_group_id == group.id)
    )
    if in_use_result.scalar_one() > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reassign this reporting group's categories before deleting it",
        )

    await log_action(
        db=db,
        action=REPORTING_GROUP_DELETED,
        entity_type="reporting_group",
        entity_id=str(group.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"name": group.name},
    )
    await db.delete(group)
    await db.commit()
    log.info("reporting_group.deleted", reporting_group_id=str(reporting_group_id), brand_id=str(brand_id))
