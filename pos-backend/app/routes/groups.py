"""Routes for Group CRUD operations."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.portal_user import PortalUser
from app.schemas.group import GroupCreate, GroupResponse, GroupUpdate
from app.services import group_service
from app.utils.dependencies import get_current_portal_user

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("/", response_model=list[GroupResponse])
async def list_groups(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: PortalUser = Depends(get_current_portal_user),
) -> list[GroupResponse]:
    """List all groups with pagination."""
    return await group_service.list_groups(db, skip=skip, limit=limit)


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: PortalUser = Depends(get_current_portal_user),
) -> GroupResponse:
    """Fetch a single group by ID."""
    return await group_service.get_group(db, group_id)


@router.post("/", response_model=GroupResponse, status_code=201)
async def create_group(
    payload: GroupCreate,
    db: AsyncSession = Depends(get_db),
    actor: PortalUser = Depends(get_current_portal_user),
) -> GroupResponse:
    """Create a new group."""
    return await group_service.create_group(db, payload, actor)


@router.patch("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: uuid.UUID,
    payload: GroupUpdate,
    db: AsyncSession = Depends(get_db),
    actor: PortalUser = Depends(get_current_portal_user),
) -> GroupResponse:
    """Update a group's name."""
    return await group_service.update_group(db, group_id, payload, actor)


@router.post("/{group_id}/suspend", response_model=GroupResponse)
async def suspend_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: PortalUser = Depends(get_current_portal_user),
) -> GroupResponse:
    """Suspend a group (set is_active = False)."""
    return await group_service.suspend_group(db, group_id, actor)


@router.post("/{group_id}/activate", response_model=GroupResponse)
async def activate_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: PortalUser = Depends(get_current_portal_user),
) -> GroupResponse:
    """Activate a previously suspended group."""
    return await group_service.activate_group(db, group_id, actor)
