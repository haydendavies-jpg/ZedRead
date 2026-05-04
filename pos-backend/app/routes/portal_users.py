"""Routes for portal user management (super_admin only)."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.portal_user import PortalUser
from app.schemas.portal_user import PortalUserCreate, PortalUserResponse, PortalUserUpdate
from app.services import portal_user_service
from app.utils.dependencies import require_super_admin

router = APIRouter(prefix="/portal-users", tags=["portal-users"])


@router.get("/", response_model=list[PortalUserResponse])
async def list_portal_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: PortalUser = Depends(require_super_admin),
) -> list[PortalUserResponse]:
    """List all portal users. Super admin only."""
    return await portal_user_service.list_portal_users(db, skip=skip, limit=limit)


@router.get("/{user_id}", response_model=PortalUserResponse)
async def get_portal_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: PortalUser = Depends(require_super_admin),
) -> PortalUserResponse:
    """Fetch a single portal user by ID. Super admin only."""
    return await portal_user_service.get_portal_user(db, user_id)


@router.post("/", response_model=PortalUserResponse, status_code=201)
async def create_portal_user(
    payload: PortalUserCreate,
    db: AsyncSession = Depends(get_db),
    actor: PortalUser = Depends(require_super_admin),
) -> PortalUserResponse:
    """Create a new portal user. Super admin only."""
    return await portal_user_service.create_portal_user(db, payload, actor)


@router.patch("/{user_id}", response_model=PortalUserResponse)
async def update_portal_user(
    user_id: uuid.UUID,
    payload: PortalUserUpdate,
    db: AsyncSession = Depends(get_db),
    actor: PortalUser = Depends(require_super_admin),
) -> PortalUserResponse:
    """Update a portal user's name or role. Super admin only."""
    return await portal_user_service.update_portal_user(db, user_id, payload, actor)


@router.post("/{user_id}/suspend", response_model=PortalUserResponse)
async def suspend_portal_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: PortalUser = Depends(require_super_admin),
) -> PortalUserResponse:
    """Suspend a portal user. Super admin only. Cannot suspend yourself."""
    return await portal_user_service.suspend_portal_user(db, user_id, actor)


@router.post("/{user_id}/activate", response_model=PortalUserResponse)
async def activate_portal_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: PortalUser = Depends(require_super_admin),
) -> PortalUserResponse:
    """Activate a suspended portal user. Super admin only."""
    return await portal_user_service.activate_portal_user(db, user_id, actor)
