"""Routes for license management (portal authenticated)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.site import Site
from app.models.user import User
from app.schemas.license import LicenseCreate, LicenseManagementUpdate, LicenseResponse, LicenseUpdate
from app.services import access_profile_service, license_service
from app.utils.dependencies import CatalogAccess, get_current_superadmin, resolve_catalog_access

router = APIRouter(prefix="/licenses", tags=["licenses"])


async def _assert_license_billing_page_granted(db: AsyncSession, access: CatalogAccess) -> None:
    """
    Authorize a management-portal license listing.

    A portal admin (portal_access) may always list licenses for whatever
    brand/site they supply. A management caller (mgmt_access) must hold the
    "license_billing" page permission — brand/site scoping for the listing
    itself is enforced by the caller filtering to access.effective_brand_id
    (mirrors settings.py's list_settings). A raw POS terminal session may
    never see billing data.

    Args:
        db: Active database session.
        access: Resolved catalog access for the calling user.

    Raises:
        HTTPException: 403 if the caller lacks the "license_billing" grant.
    """
    if access.portal_access is not None:
        return

    if access.pos_access is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    mgmt = access.mgmt_access
    assert mgmt is not None  # exactly one of the three CatalogAccess members is set

    granted_pages = await access_profile_service.list_page_permissions(db, mgmt.access_profile.id)
    if "license_billing" not in granted_pages:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


async def _assert_license_management_permitted(
    db: AsyncSession, access: CatalogAccess, license_site_id: uuid.UUID
) -> None:
    """
    Authorize a management-portal read/write of a single license.

    A portal admin (portal_access) may always manage any license. A
    management caller (mgmt_access) must hold the "license_billing" page
    permission and be scoped to the license's own site/brand — mirrors
    pos_devices.py's _assert_release_permitted. A raw POS terminal session
    may never touch licenses.

    Args:
        db: Active database session.
        access: Resolved catalog access for the calling user.
        license_site_id: The site_id of the license being read/written.

    Raises:
        HTTPException: 403 if the caller lacks permission or scope.
    """
    if access.portal_access is not None:
        return

    if access.pos_access is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    mgmt = access.mgmt_access
    assert mgmt is not None  # exactly one of the three CatalogAccess members is set

    granted_pages = await access_profile_service.list_page_permissions(db, mgmt.access_profile.id)
    if "license_billing" not in granted_pages:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    if mgmt.scope == "site":
        if mgmt.site is None or mgmt.site.id != license_site_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: license outside your site",
            )
        return

    # Brand/group scope — check the license's site belongs to the caller's brand.
    site_result = await db.execute(select(Site.brand_id).where(Site.id == license_site_id))
    site_brand_id = site_result.scalar_one_or_none()
    caller_brand_id = mgmt.brand.id if mgmt.brand else None
    if caller_brand_id is None or site_brand_id != caller_brand_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: license outside your brand",
        )


@router.get("/", response_model=list[LicenseResponse])
async def list_licenses(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=1000),
    site_id: uuid.UUID | None = Query(default=None, description="Filter by site ID"),
    status: str | None = Query(default=None, description="Exact-match filter on license status"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_superadmin),
) -> list[LicenseResponse]:
    """List all licenses with pagination and optional filters."""
    return await license_service.list_licenses(db, skip=skip, limit=limit, site_id=site_id, status=status)


@router.get("/management", response_model=list[LicenseResponse])
async def list_licenses_for_management(
    site_id: uuid.UUID | None = Query(None, description="Filter by site"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    brand_id: uuid.UUID | None = Query(None, description="Required for group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[LicenseResponse]:
    """
    List licenses within the caller's brand for the management portal's
    License & Billing page, optionally narrowed to a single site.

    A site-scope management caller is pinned to their own site regardless
    of the site_id filter — mirrors pos_devices.py's list_devices_for_management.
    """
    await _assert_license_billing_page_granted(db, access)
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
    return await license_service.list_licenses_for_brand(
        db, effective_brand_id, effective_site_id, skip=skip, limit=limit
    )


@router.get("/management/{license_id}", response_model=LicenseResponse)
async def get_license_for_management(
    license_id: uuid.UUID,
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> LicenseResponse:
    """Fetch a single license by ID via the management portal (license_billing page permission)."""
    lic = await license_service.get_license(db, license_id)
    await _assert_license_management_permitted(db, access, lic.site_id)
    return lic


@router.patch("/management/{license_id}", response_model=LicenseResponse)
async def update_license_for_management(
    license_id: uuid.UUID,
    payload: LicenseManagementUpdate,
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> LicenseResponse:
    """
    Update seat capacity on a license via the management portal.

    Restricted to the "license_billing" page permission, scoped to the
    caller's own site/brand. Commercial terms and status transitions
    (disable/enable) stay SuperAdmin-only — see LicenseManagementUpdate.
    """
    lic = await license_service.get_license(db, license_id)
    await _assert_license_management_permitted(db, access, lic.site_id)
    return await license_service.update_license(
        db, license_id, LicenseUpdate(max_devices=payload.max_devices), access.actor_user
    )


@router.get("/{license_id}", response_model=LicenseResponse)
async def get_license(
    license_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_superadmin),
) -> LicenseResponse:
    """Fetch a single license by ID."""
    return await license_service.get_license(db, license_id)


@router.post("/", response_model=LicenseResponse, status_code=201)
async def create_license(
    payload: LicenseCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> LicenseResponse:
    """Create a new license for a site. One license per site."""
    return await license_service.create_license(db, payload, actor)


@router.patch("/{license_id}", response_model=LicenseResponse)
async def update_license(
    license_id: uuid.UUID,
    payload: LicenseUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> LicenseResponse:
    """Update mutable license fields (plan name, fee, expiry)."""
    return await license_service.update_license(db, license_id, payload, actor)


@router.post("/{license_id}/disable", response_model=LicenseResponse)
async def disable_license(
    license_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> LicenseResponse:
    """Manually disable an active license."""
    return await license_service.disable_license(db, license_id, actor)


@router.post("/{license_id}/enable", response_model=LicenseResponse)
async def enable_license(
    license_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> LicenseResponse:
    """Re-enable a disabled license."""
    return await license_service.enable_license(db, license_id, actor)
