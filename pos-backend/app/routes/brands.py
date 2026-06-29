"""Routes for Brand CRUD operations."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.superadmin import SuperAdmin
from app.schemas.brand import BrandCreate, BrandResponse, BrandUpdate
from app.services import brand_service
from app.utils.dependencies import get_current_superadmin

router = APIRouter(prefix="/brands", tags=["brands"])


@router.get("/", response_model=list[BrandResponse])
async def list_brands(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    name: str | None = Query(default=None, description="Case-insensitive substring filter on brand name"),
    group_id: uuid.UUID | None = Query(default=None, description="Filter by parent group ID"),
    is_active: bool | None = Query(default=None, description="Filter by active/inactive status"),
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> list[BrandResponse]:
    """List brands with pagination and optional filters, scoped to the actor's accounts."""
    return await brand_service.list_brands(
        db, actor, skip=skip, limit=limit, name=name, group_id=group_id, is_active=is_active
    )


@router.get("/{brand_id}", response_model=BrandResponse)
async def get_brand(
    brand_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> BrandResponse:
    """Fetch a single brand by ID, scoped to the actor's accounts."""
    return await brand_service.get_brand(db, brand_id, actor)


@router.post("/", response_model=BrandResponse, status_code=201)
async def create_brand(
    payload: BrandCreate,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> BrandResponse:
    """Create a new brand. Auto-creates an 'Uncategorised' system category."""
    return await brand_service.create_brand(db, payload, actor)


@router.patch("/{brand_id}", response_model=BrandResponse)
async def update_brand(
    brand_id: uuid.UUID,
    payload: BrandUpdate,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> BrandResponse:
    """Update a brand's name."""
    return await brand_service.update_brand(db, brand_id, payload, actor)


@router.post("/{brand_id}/suspend", response_model=BrandResponse)
async def suspend_brand(
    brand_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> BrandResponse:
    """Suspend a brand (set is_active = False)."""
    return await brand_service.suspend_brand(db, brand_id, actor)


@router.post("/{brand_id}/activate", response_model=BrandResponse)
async def activate_brand(
    brand_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> BrandResponse:
    """Activate a previously suspended brand."""
    return await brand_service.activate_brand(db, brand_id, actor)
