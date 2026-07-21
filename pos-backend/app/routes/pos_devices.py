"""Routes for POS device registration (portal authenticated)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.site import Site
from app.models.user import User
from app.schemas.pos_device import PosDeviceRegister, PosDeviceResponse
from app.services import access_profile_service, pos_device_service
from app.utils.dependencies import CatalogAccess, get_current_superadmin, resolve_catalog_access

router = APIRouter(prefix="/pos-devices", tags=["pos-devices"])


async def _assert_release_permitted(
    db: AsyncSession, access: CatalogAccess, device_site_id: uuid.UUID
) -> None:
    """
    Authorize a management-portal seat release.

    A portal admin (portal_access) may always release any device, mirroring
    the existing superadmin-only /deregister escape hatch. A management
    caller (mgmt_access) must hold the "devices" page permission on their
    access profile and be scoped to the device's own site/brand. A raw POS
    terminal session (pos_access) may never release a seat — this is a
    management/admin action, not something the terminal can do to itself.

    Args:
        db: Active database session.
        access: Resolved catalog access for the calling user.
        device_site_id: The site_id of the device being released.

    Raises:
        HTTPException: 403 if the caller lacks permission or scope.
    """
    if access.portal_access is not None:
        return

    if access.pos_access is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    mgmt = access.mgmt_access
    assert mgmt is not None  # exactly one of the three CatalogAccess members is set

    granted_pages = await access_profile_service.list_page_permissions(db, mgmt.access_profile.id)
    if "devices" not in granted_pages:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    if mgmt.scope == "site":
        if mgmt.site is None or mgmt.site.id != device_site_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: device outside your site",
            )
        return

    # Brand/group scope — check the device's site belongs to the caller's brand.
    site_result = await db.execute(select(Site.brand_id).where(Site.id == device_site_id))
    site_brand_id = site_result.scalar_one_or_none()
    caller_brand_id = mgmt.brand.id if mgmt.brand else None
    if caller_brand_id is None or site_brand_id != caller_brand_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: device outside your brand",
        )


@router.get("/", response_model=list[PosDeviceResponse])
async def list_devices(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_superadmin),
) -> list[PosDeviceResponse]:
    """List all registered POS devices with pagination."""
    return await pos_device_service.list_devices(db, skip=skip, limit=limit)


@router.get("/management", response_model=list[PosDeviceResponse])
async def list_devices_for_management(
    site_id: uuid.UUID | None = Query(None, description="Filter by site"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    brand_id: uuid.UUID | None = Query(None, description="Required for group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[PosDeviceResponse]:
    """
    List devices within the caller's brand for the management portal's
    Devices page, optionally narrowed to a single site.

    A site-scope management caller is pinned to their own site regardless
    of the site_id filter — mirrors register_session_reports.py's
    _resolve_site_filter pattern.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    effective_site_id = site_id
    if access.mgmt_access and access.mgmt_access.scope == "site" and access.mgmt_access.site:
        own_site_id = access.mgmt_access.site.id
        if site_id is not None and site_id != own_site_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: report scope exceeds your site",
            )
        effective_site_id = own_site_id
    return await pos_device_service.list_devices_for_brand(
        db, effective_brand_id, effective_site_id, skip=skip, limit=limit
    )


@router.get("/{device_id}", response_model=PosDeviceResponse)
async def get_device(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_superadmin),
) -> PosDeviceResponse:
    """Fetch a single POS device by ID."""
    return await pos_device_service.get_device(db, device_id)


@router.post("/", response_model=PosDeviceResponse, status_code=201)
async def register_device(
    payload: PosDeviceRegister,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> PosDeviceResponse:
    """Register a new Android POS terminal under a site and license."""
    return await pos_device_service.register_device(db, payload, actor)


@router.post("/{device_id}/deregister", response_model=PosDeviceResponse)
async def deregister_device(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> PosDeviceResponse:
    """Deregister a POS device — marks it inactive without deleting the record."""
    return await pos_device_service.deregister_device(db, device_id, actor)


@router.post("/{device_id}/release", response_model=PosDeviceResponse)
async def release_device(
    device_id: uuid.UUID,
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> PosDeviceResponse:
    """
    Release a license seat from a device via the management portal.

    Frees the device's seat (is_active=False) so another terminal can claim
    it. Restricted to callers whose access profile is granted the
    "devices" page permission and scoped to their own site/brand; a portal
    admin may release any device.
    """
    device = await pos_device_service.get_device(db, device_id)
    await _assert_release_permitted(db, access, device.site_id)
    return await pos_device_service.deregister_device(db, device_id, access.actor_user)
