"""Routes for Group CRUD operations."""

import uuid

from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.billing_info_request import BillingInfoRequestResponse
from app.schemas.group import GroupCreate, GroupResponse, GroupUpdate
from app.services import group_service
from app.utils.dependencies import get_current_superadmin

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("/", response_model=list[GroupResponse])
async def list_groups(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=1000),
    name: str | None = Query(default=None, description="Case-insensitive substring filter on group name"),
    is_active: bool | None = Query(default=None, description="Filter by active/inactive status"),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> list[GroupResponse]:
    """List groups with pagination and optional filters, scoped to the actor's accounts."""
    return await group_service.list_groups(
        db, actor, skip=skip, limit=limit, name=name, is_active=is_active
    )


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> GroupResponse:
    """Fetch a single group by ID, scoped to the actor's accounts."""
    return await group_service.get_group(db, group_id, actor)


@router.post("/", response_model=GroupResponse, status_code=201)
async def create_group(
    payload: GroupCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> GroupResponse:
    """Create a new group."""
    return await group_service.create_group(db, payload, actor)


@router.patch("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: uuid.UUID,
    payload: GroupUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> GroupResponse:
    """Update a group's name."""
    return await group_service.update_group(db, group_id, payload, actor)


@router.post("/{group_id}/suspend", response_model=GroupResponse)
async def suspend_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> GroupResponse:
    """Suspend a group (set is_active = False)."""
    return await group_service.suspend_group(db, group_id, actor)


@router.post("/{group_id}/activate", response_model=GroupResponse)
async def activate_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> GroupResponse:
    """Activate a previously suspended group."""
    return await group_service.activate_group(db, group_id, actor)


@router.post("/{group_id}/logo", response_model=GroupResponse)
async def upload_group_logo(
    group_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> GroupResponse:
    """Upload or replace the group's logo (JPEG/PNG/WebP, up to 1 MB)."""
    return await group_service.upload_logo(db, group_id, file, actor)


@router.post("/{group_id}/request-billing-info", response_model=BillingInfoRequestResponse)
async def request_group_billing_info(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> BillingInfoRequestResponse:
    """Email the group's effective billing contact the billing_info_request template."""
    resolved = await group_service.request_billing_info(db, group_id, actor)
    return BillingInfoRequestResponse(sent_to=resolved.value, source_level=resolved.source_level)
