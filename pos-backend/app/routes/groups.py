"""Routes for Group CRUD operations."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.superadmin import SuperAdmin
from app.schemas.group import GroupCreate, GroupResponse, GroupUpdate
from app.services import group_service
from app.utils.dependencies import get_current_superadmin

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("/", response_model=list[GroupResponse])
async def list_groups(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    name: str | None = Query(default=None, description="Case-insensitive substring filter on group name"),
    is_active: bool | None = Query(default=None, description="Filter by active/inactive status"),
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> list[GroupResponse]:
    """List groups with pagination and optional filters, scoped to the actor's accounts."""
    return await group_service.list_groups(
        db, actor, skip=skip, limit=limit, name=name, is_active=is_active
    )


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> GroupResponse:
    """Fetch a single group by ID, scoped to the actor's accounts."""
    return await group_service.get_group(db, group_id, actor)


@router.post("/", response_model=GroupResponse, status_code=201)
async def create_group(
    payload: GroupCreate,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> GroupResponse:
    """Create a new group."""
    return await group_service.create_group(db, payload, actor)


@router.patch("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: uuid.UUID,
    payload: GroupUpdate,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> GroupResponse:
    """Update a group's name."""
    return await group_service.update_group(db, group_id, payload, actor)


@router.post("/{group_id}/suspend", response_model=GroupResponse)
async def suspend_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> GroupResponse:
    """Suspend a group (set is_active = False)."""
    return await group_service.suspend_group(db, group_id, actor)


@router.post("/{group_id}/activate", response_model=GroupResponse)
async def activate_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> GroupResponse:
    """Activate a previously suspended group."""
    return await group_service.activate_group(db, group_id, actor)
