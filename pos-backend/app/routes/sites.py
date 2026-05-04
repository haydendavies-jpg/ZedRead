"""Routes for Site CRUD operations."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.portal_user import PortalUser
from app.schemas.site import SiteCreate, SiteResponse, SiteUpdate
from app.services import site_service
from app.utils.dependencies import get_current_portal_user

router = APIRouter(prefix="/sites", tags=["sites"])


@router.get("/", response_model=list[SiteResponse])
async def list_sites(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: PortalUser = Depends(get_current_portal_user),
) -> list[SiteResponse]:
    """List all sites with pagination."""
    return await site_service.list_sites(db, skip=skip, limit=limit)


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: PortalUser = Depends(get_current_portal_user),
) -> SiteResponse:
    """Fetch a single site by ID."""
    return await site_service.get_site(db, site_id)


@router.post("/", response_model=SiteResponse, status_code=201)
async def create_site(
    payload: SiteCreate,
    db: AsyncSession = Depends(get_db),
    actor: PortalUser = Depends(get_current_portal_user),
) -> SiteResponse:
    """Create a new site under a brand."""
    return await site_service.create_site(db, payload, actor)


@router.patch("/{site_id}", response_model=SiteResponse)
async def update_site(
    site_id: uuid.UUID,
    payload: SiteUpdate,
    db: AsyncSession = Depends(get_db),
    actor: PortalUser = Depends(get_current_portal_user),
) -> SiteResponse:
    """Update a site's name."""
    return await site_service.update_site(db, site_id, payload, actor)


@router.post("/{site_id}/suspend", response_model=SiteResponse)
async def suspend_site(
    site_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: PortalUser = Depends(get_current_portal_user),
) -> SiteResponse:
    """Suspend a site (set is_active = False)."""
    return await site_service.suspend_site(db, site_id, actor)


@router.post("/{site_id}/activate", response_model=SiteResponse)
async def activate_site(
    site_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: PortalUser = Depends(get_current_portal_user),
) -> SiteResponse:
    """Activate a previously suspended site."""
    return await site_service.activate_site(db, site_id, actor)
