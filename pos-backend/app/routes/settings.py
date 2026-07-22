"""Routes for the POS settings framework (Android POS Phase 2).

Management CRUD lives under /settings (portal/management JWT, gated by the
"site_settings" page permission — see app/constants/pages.py). The POS
terminal's own read-only view lives under /pos/settings, mirroring the
/pos/menu-layout consumption contract in routes/menu_layouts.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.statuses import SystemAccessProfile
from app.database import get_db
from app.schemas.setting import SettingOut, SettingUpdateRequest
from app.services import access_profile_service, settings_service
from app.utils.dependencies import CatalogAccess, POSAccess, resolve_access, resolve_catalog_access

router = APIRouter(prefix="/settings", tags=["settings"])
pos_router = APIRouter(prefix="/pos", tags=["pos"])

# A POS terminal may push its own site's settings back to become the
# backend default ("Save as default") only when the operator's POS access
# profile is one of these three named system tiers. Deliberately an explicit
# allow-list rather than access_grant_service.role_rank()'s ladder: that
# helper ranks an unrecognised (custom) profile name at Admin tier by
# design — the safe default for its own use case (a delegation ceiling,
# where under-ranking a legitimate senior custom role is the bigger risk)
# but the wrong direction here, where an unverified custom profile should
# NOT be assumed capable of overwriting a site's backend settings.
_POS_SETTINGS_WRITE_PROFILE_NAMES = frozenset(
    {SystemAccessProfile.MASTER.value, SystemAccessProfile.ADMIN.value, SystemAccessProfile.MANAGER.value}
)


async def _assert_settings_permitted(
    db: AsyncSession, access: CatalogAccess, target_site_id: uuid.UUID | None
) -> None:
    """
    Authorize a management-portal settings read/write.

    A portal admin (portal_access) may always manage settings for whatever
    brand/site they supply. A management caller (mgmt_access) must hold the
    "site_settings" page permission and be scoped to the target site — a
    site-scope caller may only touch their own site (or the brand-level
    default, target_site_id=None is allowed through since a brand default
    isn't site-specific and mgmt.brand already pins the brand). A POS
    terminal session (pos_access) may push a "Save as default" override for
    its own site only, and only when its access profile is Manager tier or
    above (see _POS_SETTINGS_WRITE_PROFILE_NAMES) — Staff/Reporting Only,
    and any custom (non-system) profile, still only read via GET /pos/settings.

    Args:
        db: Active database session.
        access: Resolved catalog access for the calling user.
        target_site_id: The site_id being read/written, or None for a
            brand-level default.

    Raises:
        HTTPException: 403 if the caller lacks permission or scope.
    """
    if access.portal_access is not None:
        return

    if access.pos_access is not None:
        if access.pos_access.access_profile.name not in _POS_SETTINGS_WRITE_PROFILE_NAMES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        if target_site_id is not None and target_site_id != access.pos_access.site.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: setting outside your site",
            )
        return

    mgmt = access.mgmt_access
    assert mgmt is not None  # exactly one of the three CatalogAccess members is set

    granted_pages = await access_profile_service.list_page_permissions(db, mgmt.access_profile.id)
    if "site_settings" not in granted_pages:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    if mgmt.scope == "site" and target_site_id is not None:
        if mgmt.site is None or mgmt.site.id != target_site_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: setting outside your site",
            )


@router.get("", response_model=list[SettingOut], status_code=status.HTTP_200_OK)
async def list_settings(
    site_id: uuid.UUID | None = Query(None, description="Also resolve site-level overrides for this site"),
    search: str | None = Query(None, description="Case-insensitive filter on key/label/category"),
    brand_id: uuid.UUID | None = Query(None, description="Required for group-scope or portal admin access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[SettingOut]:
    """
    List the setting catalog merged with brand/site override state.

    A site-scope management caller is pinned to their own site regardless
    of the site_id filter — mirrors pos_devices.py's list_devices_for_management.
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

    await _assert_settings_permitted(db, access, effective_site_id)
    return await settings_service.list_settings_for_scope(db, effective_brand_id, effective_site_id, search)


@router.put("/{key}", response_model=SettingOut, status_code=status.HTTP_200_OK)
async def update_setting(
    key: str,
    payload: SettingUpdateRequest,
    brand_id: uuid.UUID | None = Query(None, description="Required for group-scope or portal admin access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> SettingOut:
    """Set a brand- or site-level override for one setting."""
    effective_brand_id = access.effective_brand_id(brand_id)
    await _assert_settings_permitted(db, access, payload.site_id)
    return await settings_service.upsert_setting(
        db, key, payload.value, effective_brand_id, payload.site_id, access.actor_user
    )


@router.delete("/{key}", response_model=SettingOut, status_code=status.HTTP_200_OK)
async def reset_setting(
    key: str,
    site_id: uuid.UUID | None = Query(None, description="Clear this site's override, or omit for the brand default"),
    brand_id: uuid.UUID | None = Query(None, description="Required for group-scope or portal admin access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> SettingOut:
    """Clear a brand- or site-level override, reverting to its fallback."""
    effective_brand_id = access.effective_brand_id(brand_id)
    await _assert_settings_permitted(db, access, site_id)
    return await settings_service.clear_setting_override(
        db, key, effective_brand_id, site_id, access.actor_user
    )


@pos_router.get("/settings", response_model=list[SettingOut], status_code=status.HTTP_200_OK)
async def get_pos_settings(
    search: str | None = Query(None, description="Case-insensitive filter on key/label/category"),
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> list[SettingOut]:
    """
    Read-only settings contract for the Android app: every setting resolved
    for the terminal's own site (site override → brand default → catalog
    default), searchable client-side or via the search query param.
    """
    return await settings_service.get_effective_settings_for_site(db, access.site, search)
