"""Routes for Brand CRUD operations."""

import uuid

from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.billing_info_request import BillingInfoRequestResponse
from app.schemas.brand import BrandCreate, BrandResponse, BrandUpdate
from app.services import brand_service
from app.utils.dependencies import ManagementAccess, get_current_superadmin, resolve_portal_or_management

router = APIRouter(prefix="/brands", tags=["brands"])


@router.get("/", response_model=list[BrandResponse])
async def list_brands(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=1000),
    name: str | None = Query(default=None, description="Case-insensitive substring filter on brand name"),
    group_id: uuid.UUID | None = Query(default=None, description="Filter by parent group ID"),
    is_active: bool | None = Query(default=None, description="Filter by active/inactive status"),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> list[BrandResponse]:
    """List brands with pagination and optional filters, scoped to the actor's accounts."""
    return await brand_service.list_brands(
        db, actor, skip=skip, limit=limit, name=name, group_id=group_id, is_active=is_active
    )


@router.get("/{brand_id}", response_model=BrandResponse)
async def get_brand(
    brand_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User | ManagementAccess = Depends(resolve_portal_or_management),
) -> BrandResponse:
    """Fetch a single brand by ID, scoped to the actor's accounts (or a management caller's own scope)."""
    return await brand_service.get_brand(db, brand_id, actor)


@router.post("/", response_model=BrandResponse, status_code=201)
async def create_brand(
    payload: BrandCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> BrandResponse:
    """Create a new brand. Auto-creates an 'Uncategorised' system category."""
    return await brand_service.create_brand(db, payload, actor)


@router.patch("/{brand_id}", response_model=BrandResponse)
async def update_brand(
    brand_id: uuid.UUID,
    payload: BrandUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User | ManagementAccess = Depends(resolve_portal_or_management),
) -> BrandResponse:
    """Update a brand's company profile fields."""
    return await brand_service.update_brand(db, brand_id, payload, actor)


@router.post("/{brand_id}/suspend", response_model=BrandResponse)
async def suspend_brand(
    brand_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> BrandResponse:
    """Suspend a brand (set is_active = False)."""
    return await brand_service.suspend_brand(db, brand_id, actor)


@router.post("/{brand_id}/activate", response_model=BrandResponse)
async def activate_brand(
    brand_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> BrandResponse:
    """Activate a previously suspended brand."""
    return await brand_service.activate_brand(db, brand_id, actor)


@router.post("/{brand_id}/logo", response_model=BrandResponse)
async def upload_brand_logo(
    brand_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    actor: User | ManagementAccess = Depends(resolve_portal_or_management),
) -> BrandResponse:
    """Upload or replace the brand's logo (JPEG/PNG/WebP, up to 1 MB)."""
    return await brand_service.upload_logo(db, brand_id, file, actor)


@router.post("/{brand_id}/request-billing-info", response_model=BillingInfoRequestResponse)
async def request_brand_billing_info(
    brand_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User | ManagementAccess = Depends(resolve_portal_or_management),
) -> BillingInfoRequestResponse:
    """Email the brand's effective billing contact the billing_info_request template."""
    resolved = await brand_service.request_billing_info(db, brand_id, actor)
    return BillingInfoRequestResponse(sent_to=resolved.value, source_level=resolved.source_level)
