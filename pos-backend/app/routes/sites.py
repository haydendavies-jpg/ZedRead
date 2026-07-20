"""Routes for Site CRUD operations."""

import uuid

from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.billing_info_request import BillingInfoRequestResponse
from app.schemas.site import SiteCreate, SiteResponse, SiteUpdate
from app.services import site_service
from app.utils.dependencies import get_current_superadmin

router = APIRouter(prefix="/sites", tags=["sites"])


@router.get("/", response_model=list[SiteResponse])
async def list_sites(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=1000),
    name: str | None = Query(default=None, description="Case-insensitive substring filter on site name"),
    brand_id: uuid.UUID | None = Query(default=None, description="Filter by parent brand ID"),
    is_active: bool | None = Query(default=None, description="Filter by active/inactive status"),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> list[SiteResponse]:
    """List sites with pagination and optional filters, scoped to the actor's accounts."""
    return await site_service.list_sites(
        db, actor, skip=skip, limit=limit, name=name, brand_id=brand_id, is_active=is_active
    )


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> SiteResponse:
    """Fetch a single site by ID, scoped to the actor's accounts."""
    return await site_service.get_site(db, site_id, actor)


@router.post("/", response_model=SiteResponse, status_code=201)
async def create_site(
    payload: SiteCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> SiteResponse:
    """Create a new site under a brand."""
    return await site_service.create_site(db, payload, actor)


@router.patch("/{site_id}", response_model=SiteResponse)
async def update_site(
    site_id: uuid.UUID,
    payload: SiteUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> SiteResponse:
    """Update a site's name."""
    return await site_service.update_site(db, site_id, payload, actor)


@router.post("/{site_id}/suspend", response_model=SiteResponse)
async def suspend_site(
    site_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> SiteResponse:
    """Suspend a site (set is_active = False)."""
    return await site_service.suspend_site(db, site_id, actor)


@router.post("/{site_id}/activate", response_model=SiteResponse)
async def activate_site(
    site_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> SiteResponse:
    """Activate a previously suspended site."""
    return await site_service.activate_site(db, site_id, actor)


@router.post("/{site_id}/logo", response_model=SiteResponse)
async def upload_site_logo(
    site_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> SiteResponse:
    """Upload or replace the site's logo (JPEG/PNG/WebP, up to 1 MB)."""
    return await site_service.upload_logo(db, site_id, file, actor)


@router.post("/{site_id}/request-billing-info", response_model=BillingInfoRequestResponse)
async def request_site_billing_info(
    site_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> BillingInfoRequestResponse:
    """Email the site's effective billing contact the billing_info_request template."""
    resolved = await site_service.request_billing_info(db, site_id, actor)
    return BillingInfoRequestResponse(sent_to=resolved.value, source_level=resolved.source_level)
