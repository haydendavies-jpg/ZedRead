"""Routes for portal user management (Admin-role SuperAdmin only)."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.superadmin import SuperAdmin
from app.schemas.superadmin import SuperAdminCreate, SuperAdminResponse, SuperAdminUpdate
from app.services import superadmin_service
from app.utils.dependencies import require_super_admin

router = APIRouter(prefix="/portal-users", tags=["portal-users"])


@router.get("/", response_model=list[SuperAdminResponse])
async def list_superadmins(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    email: str | None = Query(default=None, description="Case-insensitive substring filter on email address"),
    role: str | None = Query(default=None, description="Exact-match filter on user role"),
    is_active: bool | None = Query(default=None, description="Filter by active/inactive status"),
    db: AsyncSession = Depends(get_db),
    _: SuperAdmin = Depends(require_super_admin),
) -> list[SuperAdminResponse]:
    """List all portal users with optional filters. Super admin only."""
    return await superadmin_service.list_superadmins(db, skip=skip, limit=limit, email=email, role=role, is_active=is_active)


@router.get("/{user_id}", response_model=SuperAdminResponse)
async def get_superadmin(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: SuperAdmin = Depends(require_super_admin),
) -> SuperAdminResponse:
    """Fetch a single portal user by ID. Super admin only."""
    return await superadmin_service.get_superadmin(db, user_id)


@router.post("/", response_model=SuperAdminResponse, status_code=201)
async def create_superadmin(
    payload: SuperAdminCreate,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(require_super_admin),
) -> SuperAdminResponse:
    """Create a new portal user. Super admin only."""
    return await superadmin_service.create_superadmin(db, payload, actor)


@router.patch("/{user_id}", response_model=SuperAdminResponse)
async def update_superadmin(
    user_id: uuid.UUID,
    payload: SuperAdminUpdate,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(require_super_admin),
) -> SuperAdminResponse:
    """Update a portal user's name or role. Super admin only."""
    return await superadmin_service.update_superadmin(db, user_id, payload, actor)


@router.post("/{user_id}/suspend", response_model=SuperAdminResponse)
async def suspend_superadmin(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(require_super_admin),
) -> SuperAdminResponse:
    """Suspend a portal user. Super admin only. Cannot suspend yourself."""
    return await superadmin_service.suspend_superadmin(db, user_id, actor)


@router.post("/{user_id}/activate", response_model=SuperAdminResponse)
async def activate_superadmin(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(require_super_admin),
) -> SuperAdminResponse:
    """Activate a suspended portal user. Super admin only."""
    return await superadmin_service.activate_superadmin(db, user_id, actor)
