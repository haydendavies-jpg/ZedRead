"""Business logic for Group CRUD operations."""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    GROUP_ACTIVATED,
    GROUP_CREATED,
    GROUP_SUSPENDED,
    GROUP_UPDATED,
)
from app.models.group import Group
from app.models.portal_user import PortalUser
from app.schemas.group import GroupCreate, GroupUpdate
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


async def _get_or_404(db: AsyncSession, group_id: uuid.UUID) -> Group:
    """
    Fetch a Group by ID or raise HTTP 404.

    Args:
        db: Active database session.
        group_id: The UUID of the group to fetch.

    Returns:
        Group: The found group instance.

    Raises:
        HTTPException: 404 if no group with the given ID exists.
    """
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return group


async def list_groups(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    name: str | None = None,
    is_active: bool | None = None,
) -> list[Group]:
    """
    Return a paginated list of all groups with optional filters.

    Args:
        db: Active database session.
        skip: Number of records to skip (offset).
        limit: Maximum number of records to return.
        name: Optional substring filter on Group.name (case-insensitive).
        is_active: Optional exact-match filter on Group.is_active.

    Returns:
        list[Group]: The requested page of groups.
    """
    conditions: list = []
    if name is not None:
        # Case-insensitive partial match using SQL ILIKE
        conditions.append(Group.name.ilike(f"%{name}%"))
    if is_active is not None:
        conditions.append(Group.is_active == is_active)

    result = await db.execute(
        select(Group).where(*conditions).order_by(Group.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def get_group(db: AsyncSession, group_id: uuid.UUID) -> Group:
    """
    Fetch a single group by ID.

    Args:
        db: Active database session.
        group_id: The UUID of the group.

    Returns:
        Group: The found group.

    Raises:
        HTTPException: 404 if the group does not exist.
    """
    return await _get_or_404(db, group_id)


async def create_group(
    db: AsyncSession,
    payload: GroupCreate,
    actor: PortalUser,
) -> Group:
    """
    Create a new Group and write an audit log row in the same transaction.

    Args:
        db: Active database session.
        payload: The group creation data.
        actor: The authenticated portal user performing the action.

    Returns:
        Group: The newly created group.
    """
    log.info("group.creating", name=payload.name, actor_id=str(actor.id))

    group = Group(id=uuid.uuid4(), name=payload.name, is_active=True)
    db.add(group)

    await log_action(
        db=db,
        action=GROUP_CREATED,
        entity_type="group",
        entity_id=str(group.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"name": group.name, "is_active": group.is_active},
    )

    await db.commit()
    await db.refresh(group)
    log.info("group.created", group_id=str(group.id))
    return group


async def update_group(
    db: AsyncSession,
    group_id: uuid.UUID,
    payload: GroupUpdate,
    actor: PortalUser,
) -> Group:
    """
    Update a Group's mutable fields and write an audit log row.

    Args:
        db: Active database session.
        group_id: The UUID of the group to update.
        payload: The fields to update (all optional).
        actor: The authenticated portal user performing the action.

    Returns:
        Group: The updated group.

    Raises:
        HTTPException: 404 if the group does not exist.
    """
    group = await _get_or_404(db, group_id)

    before = {"name": group.name}
    if payload.name is not None:
        group.name = payload.name
    after = {"name": group.name}

    await log_action(
        db=db,
        action=GROUP_UPDATED,
        entity_type="group",
        entity_id=str(group.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after,
    )

    await db.commit()
    await db.refresh(group)
    return group


async def suspend_group(
    db: AsyncSession,
    group_id: uuid.UUID,
    actor: PortalUser,
) -> Group:
    """
    Set a Group's is_active flag to False and write an audit log row.

    Args:
        db: Active database session.
        group_id: The UUID of the group to suspend.
        actor: The authenticated portal user performing the action.

    Returns:
        Group: The suspended group.

    Raises:
        HTTPException: 404 if the group does not exist.
        HTTPException: 409 if the group is already suspended.
    """
    group = await _get_or_404(db, group_id)

    if not group.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group is already suspended")

    group.is_active = False

    await log_action(
        db=db,
        action=GROUP_SUSPENDED,
        entity_type="group",
        entity_id=str(group.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": True},
        after_state={"is_active": False},
    )

    await db.commit()
    await db.refresh(group)
    return group


async def activate_group(
    db: AsyncSession,
    group_id: uuid.UUID,
    actor: PortalUser,
) -> Group:
    """
    Set a Group's is_active flag to True and write an audit log row.

    Args:
        db: Active database session.
        group_id: The UUID of the group to activate.
        actor: The authenticated portal user performing the action.

    Returns:
        Group: The activated group.

    Raises:
        HTTPException: 404 if the group does not exist.
        HTTPException: 409 if the group is already active.
    """
    group = await _get_or_404(db, group_id)

    if group.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group is already active")

    group.is_active = True

    await log_action(
        db=db,
        action=GROUP_ACTIVATED,
        entity_type="group",
        entity_id=str(group.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": False},
        after_state={"is_active": True},
    )

    await db.commit()
    await db.refresh(group)
    return group
