"""Routes for license management (portal authenticated)."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.superadmin import SuperAdmin
from app.schemas.license import LicenseCreate, LicenseResponse, LicenseUpdate
from app.services import license_service
from app.utils.dependencies import get_current_superadmin

router = APIRouter(prefix="/licenses", tags=["licenses"])


@router.get("/", response_model=list[LicenseResponse])
async def list_licenses(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    site_id: uuid.UUID | None = Query(default=None, description="Filter by site ID"),
    status: str | None = Query(default=None, description="Exact-match filter on license status"),
    db: AsyncSession = Depends(get_db),
    _: SuperAdmin = Depends(get_current_superadmin),
) -> list[LicenseResponse]:
    """List all licenses with pagination and optional filters."""
    return await license_service.list_licenses(db, skip=skip, limit=limit, site_id=site_id, status=status)


@router.get("/{license_id}", response_model=LicenseResponse)
async def get_license(
    license_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: SuperAdmin = Depends(get_current_superadmin),
) -> LicenseResponse:
    """Fetch a single license by ID."""
    return await license_service.get_license(db, license_id)


@router.post("/", response_model=LicenseResponse, status_code=201)
async def create_license(
    payload: LicenseCreate,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> LicenseResponse:
    """Create a new license for a site. One license per site."""
    return await license_service.create_license(db, payload, actor)


@router.patch("/{license_id}", response_model=LicenseResponse)
async def update_license(
    license_id: uuid.UUID,
    payload: LicenseUpdate,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> LicenseResponse:
    """Update mutable license fields (plan name, fee, expiry)."""
    return await license_service.update_license(db, license_id, payload, actor)


@router.post("/{license_id}/disable", response_model=LicenseResponse)
async def disable_license(
    license_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> LicenseResponse:
    """Manually disable an active license."""
    return await license_service.disable_license(db, license_id, actor)


@router.post("/{license_id}/enable", response_model=LicenseResponse)
async def enable_license(
    license_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(get_current_superadmin),
) -> LicenseResponse:
    """Re-enable a disabled license."""
    return await license_service.enable_license(db, license_id, actor)
