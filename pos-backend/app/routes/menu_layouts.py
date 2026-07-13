"""POS Menu Builder routes (Stage 23; Phase 2 grid editor).

Management CRUD lives under /menu-layouts (portal/management JWT only — POS
terminal tokens are read-only via the /pos/menu-layout consumption contract
below). Tabs nest arbitrarily deep via parent_tab_id and buttons are either
kind='product' or kind='folder' (Menu Studio redesign, Phase 2).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.site import Site
from app.schemas.menu_layout import (
    MenuButtonCreate,
    MenuButtonOut,
    MenuButtonsBulkColor,
    MenuButtonsBulkDelete,
    MenuButtonsGroupIntoTab,
    MenuButtonsReorder,
    MenuButtonUpdate,
    MenuLayoutCreate,
    MenuLayoutDetail,
    MenuLayoutOut,
    MenuLayoutSchedulePublish,
    MenuLayoutUpdate,
    MenuTabCreate,
    MenuTabOut,
    MenuTabsReorder,
    MenuTabUpdate,
    PublishResult,
)
from app.services import menu_builder_service
from app.services.report_service import _assert_site_scope
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(prefix="/menu-layouts", tags=["menu-layouts"])
pos_router = APIRouter(prefix="/pos", tags=["pos"])


def _require_management(access: CatalogAccess) -> None:
    """
    Reject POS terminal tokens from menu builder write/detail operations.

    Args:
        access: Resolved catalog access for the current request.

    Raises:
        HTTPException: 403 if the caller authenticated with a POS terminal JWT.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Menu builder requires a management or portal JWT",
        )


def _to_detail(data: dict) -> MenuLayoutDetail:
    """
    Build a MenuLayoutDetail response from the service's {'layout', 'tabs'} dict.

    Args:
        data: Dict with keys 'layout' (MenuLayout ORM row) and 'tabs' (list[MenuTabOut]).

    Returns:
        MenuLayoutDetail: The combined response schema.
    """
    base = MenuLayoutOut.model_validate(data["layout"]).model_dump()
    return MenuLayoutDetail(**base, tabs=data["tabs"])


# ── Layouts ───────────────────────────────────────────────────────────────────


@router.get("", response_model=list[MenuLayoutOut], status_code=status.HTTP_200_OK)
async def list_menu_layouts(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    site_id: uuid.UUID | None = Query(None, description="Filter to layouts visible to this site"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[MenuLayoutOut]:
    """List menu layouts for the authenticated user's brand, each with its total button count."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    rows = await menu_builder_service.list_menu_layouts(db, effective_brand_id, site_id, skip, limit)
    results = []
    for layout, count in rows:
        out = MenuLayoutOut.model_validate(layout)
        out.button_count = count
        results.append(out)
    return results


@router.post("", response_model=MenuLayoutOut, status_code=status.HTTP_201_CREATED)
async def create_menu_layout(
    payload: MenuLayoutCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuLayoutOut:
    """Create a new menu layout."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    layout = await menu_builder_service.create_menu_layout(db, effective_brand_id, payload, access.actor_user)
    return MenuLayoutOut.model_validate(layout)


@router.get("/{layout_id}", response_model=MenuLayoutDetail, status_code=status.HTTP_200_OK)
async def get_menu_layout(
    layout_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuLayoutDetail:
    """Fetch a menu layout with its full flat tab tree and resolved buttons."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    data = await menu_builder_service.get_menu_layout_detail(db, effective_brand_id, layout_id)
    return _to_detail(data)


@router.patch("/{layout_id}", response_model=MenuLayoutOut, status_code=status.HTTP_200_OK)
async def update_menu_layout(
    layout_id: uuid.UUID,
    payload: MenuLayoutUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuLayoutOut:
    """Update a menu layout's mutable fields, including active-time/day-of-week scheduling."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    layout = await menu_builder_service.update_menu_layout(
        db, effective_brand_id, layout_id, payload, access.actor_user
    )
    return MenuLayoutOut.model_validate(layout)


@router.delete("/{layout_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def delete_menu_layout(
    layout_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a menu layout and its tabs/buttons."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    await menu_builder_service.delete_menu_layout(db, effective_brand_id, layout_id, access.actor_user)


@router.post("/{layout_id}/duplicate", response_model=MenuLayoutOut, status_code=status.HTTP_201_CREATED)
async def duplicate_menu_layout(
    layout_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuLayoutOut:
    """Duplicate a layout and its full tab tree + buttons. The copy starts unpublished, unscheduled."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    layout = await menu_builder_service.duplicate_menu_layout(db, effective_brand_id, layout_id, access.actor_user)
    return MenuLayoutOut.model_validate(layout)


@router.post("/{layout_id}/publish", response_model=PublishResult, status_code=status.HTTP_200_OK)
async def publish_menu_layout(
    layout_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> PublishResult:
    """Publish a menu layout. Stale button refs produce warnings, not a failed publish."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    layout, warnings = await menu_builder_service.publish_menu_layout(
        db, effective_brand_id, layout_id, access.actor_user
    )
    return PublishResult(layout=MenuLayoutOut.model_validate(layout), warnings=warnings)


@router.post("/{layout_id}/unpublish", response_model=MenuLayoutOut, status_code=status.HTTP_200_OK)
async def unpublish_menu_layout(
    layout_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuLayoutOut:
    """Unpublish a menu layout."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    layout = await menu_builder_service.unpublish_menu_layout(db, effective_brand_id, layout_id, access.actor_user)
    return MenuLayoutOut.model_validate(layout)


@router.post("/{layout_id}/schedule-publish", response_model=MenuLayoutOut, status_code=status.HTTP_200_OK)
async def schedule_layout_publish(
    layout_id: uuid.UUID,
    payload: MenuLayoutSchedulePublish,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuLayoutOut:
    """Set a layout's future 'Schedule publish' target time (persisted only — see MenuLayout docstring)."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    layout = await menu_builder_service.schedule_layout_publish(
        db, effective_brand_id, layout_id, payload.scheduled_publish_at, access.actor_user
    )
    return MenuLayoutOut.model_validate(layout)


@router.post("/{layout_id}/cancel-schedule-publish", response_model=MenuLayoutOut, status_code=status.HTTP_200_OK)
async def cancel_layout_scheduled_publish(
    layout_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuLayoutOut:
    """Cancel a layout's pending 'Schedule publish'."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    layout = await menu_builder_service.cancel_layout_scheduled_publish(
        db, effective_brand_id, layout_id, access.actor_user
    )
    return MenuLayoutOut.model_validate(layout)


# ── Tabs ──────────────────────────────────────────────────────────────────────


@router.post("/{layout_id}/tabs", response_model=MenuTabOut, status_code=status.HTTP_201_CREATED)
async def create_menu_tab(
    layout_id: uuid.UUID,
    payload: MenuTabCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuTabOut:
    """Add a tab to a menu layout — top-level (rail) tab, or nested when parent_tab_id is given."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    tab = await menu_builder_service.create_menu_tab(db, effective_brand_id, layout_id, payload, access.actor_user)
    return MenuTabOut(
        id=tab.id,
        layout_id=tab.layout_id,
        parent_tab_id=tab.parent_tab_id,
        name=tab.name,
        color=tab.color,
        display_order=tab.display_order,
        buttons=[],
    )


@router.patch("/{layout_id}/tabs/{tab_id}", response_model=MenuTabOut, status_code=status.HTTP_200_OK)
async def update_menu_tab(
    layout_id: uuid.UUID,
    tab_id: uuid.UUID,
    payload: MenuTabUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuTabOut:
    """Update a menu tab's mutable fields (name/color)."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    tab = await menu_builder_service.update_menu_tab(
        db, effective_brand_id, layout_id, tab_id, payload, access.actor_user
    )
    data = await menu_builder_service.get_menu_layout_detail(db, effective_brand_id, layout_id)
    return next(t for t in data["tabs"] if t.id == tab.id)


@router.delete("/{layout_id}/tabs/{tab_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def delete_menu_tab(
    layout_id: uuid.UUID,
    tab_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a menu tab, its nested child tabs, and their buttons."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    await menu_builder_service.delete_menu_tab(db, effective_brand_id, layout_id, tab_id, access.actor_user)


@router.post("/{layout_id}/tabs/reorder", response_model=list[MenuTabOut], status_code=status.HTTP_200_OK)
async def reorder_menu_tabs(
    layout_id: uuid.UUID,
    payload: MenuTabsReorder,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[MenuTabOut]:
    """Reorder a set of sibling tabs — every tab_id gets display_order = its list index."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    await menu_builder_service.reorder_menu_tabs(
        db, effective_brand_id, layout_id, payload.tab_ids, access.actor_user
    )
    data = await menu_builder_service.get_menu_layout_detail(db, effective_brand_id, layout_id)
    return data["tabs"]


# ── Buttons ───────────────────────────────────────────────────────────────────


@router.post(
    "/{layout_id}/tabs/{tab_id}/buttons", response_model=MenuButtonOut, status_code=status.HTTP_201_CREATED
)
async def create_menu_button(
    layout_id: uuid.UUID,
    tab_id: uuid.UUID,
    payload: MenuButtonCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuButtonOut:
    """Add a button to a tab — a product tile resolved live by ref code, or a folder that opens a new nested tab."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    return await menu_builder_service.create_menu_button(
        db, effective_brand_id, layout_id, tab_id, payload, access.actor_user
    )


@router.patch(
    "/{layout_id}/tabs/{tab_id}/buttons/{button_id}", response_model=MenuButtonOut, status_code=status.HTTP_200_OK
)
async def update_menu_button(
    layout_id: uuid.UUID,
    tab_id: uuid.UUID,
    button_id: uuid.UUID,
    payload: MenuButtonUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuButtonOut:
    """Update a button's mutable fields — resize, recolor, or relink a product (inspector panel)."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    return await menu_builder_service.update_menu_button(
        db, effective_brand_id, layout_id, tab_id, button_id, payload, access.actor_user
    )


@router.delete(
    "/{layout_id}/tabs/{tab_id}/buttons/{button_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT
)
async def delete_menu_button(
    layout_id: uuid.UUID,
    tab_id: uuid.UUID,
    button_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a button from a tab. A folder button's nested tab (and its buttons) cascade-deletes too."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    await menu_builder_service.delete_menu_button(
        db, effective_brand_id, layout_id, tab_id, button_id, access.actor_user
    )


@router.post(
    "/{layout_id}/tabs/{tab_id}/buttons/reorder", response_model=MenuTabOut, status_code=status.HTTP_200_OK
)
async def reorder_menu_buttons(
    layout_id: uuid.UUID,
    tab_id: uuid.UUID,
    payload: MenuButtonsReorder,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuTabOut:
    """
    Reorder (and/or move into) this tab's buttons.

    Every listed button_id is reassigned to this tab and re-numbered by list
    index — a button dragged in from another tab only needs one call, against
    the destination tab.
    """
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    return await menu_builder_service.reorder_menu_buttons(
        db, effective_brand_id, layout_id, tab_id, payload.button_ids, access.actor_user
    )


@router.post(
    "/{layout_id}/buttons/bulk-recolor", response_model=list[uuid.UUID], status_code=status.HTTP_200_OK
)
async def bulk_recolor_menu_buttons(
    layout_id: uuid.UUID,
    payload: MenuButtonsBulkColor,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[uuid.UUID]:
    """Bulk-recolor a multi-selection of buttons (the grid editor's floating action bar)."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    return await menu_builder_service.bulk_recolor_menu_buttons(
        db, effective_brand_id, layout_id, payload.button_ids, payload.color, access.actor_user
    )


@router.post("/{layout_id}/buttons/bulk-delete", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def bulk_delete_menu_buttons(
    layout_id: uuid.UUID,
    payload: MenuButtonsBulkDelete,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Bulk-delete a multi-selection of buttons (folder buttons' nested tabs cascade too)."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    await menu_builder_service.bulk_delete_menu_buttons(
        db, effective_brand_id, layout_id, payload.button_ids, access.actor_user
    )


@router.post(
    "/{layout_id}/buttons/group-into-tab", response_model=MenuButtonOut, status_code=status.HTTP_201_CREATED
)
async def group_menu_buttons_into_tab(
    layout_id: uuid.UUID,
    payload: MenuButtonsGroupIntoTab,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuButtonOut:
    """Bundle a multi-selection of buttons into a newly created nested tab, leaving a folder button behind."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    return await menu_builder_service.group_menu_buttons_into_tab(
        db, effective_brand_id, layout_id, payload.button_ids, payload.name, access.actor_user
    )


# ── POS consumption contract ──────────────────────────────────────────────────


@pos_router.get("/menu-layout", response_model=list[MenuLayoutDetail], status_code=status.HTTP_200_OK)
async def get_pos_menu_layout(
    site_id: uuid.UUID = Query(..., description="Site to resolve published menu layouts for"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[MenuLayoutDetail]:
    """
    Publish contract for the Android app: every currently-active published layout visible to a site.

    Includes brand-wide published layouts and any site-specific published
    layout for site_id — more than one may be returned at once (e.g. per-site
    or day-part menus), filtered further by each layout's own active-time/
    day-of-week window. Android-side consumption is out of scope for this
    stage; this route builds the contract only.
    """
    if access.pos_access:
        _assert_site_scope(site_id, access.pos_access.site.id)
    elif access.mgmt_access and access.mgmt_access.scope == "site" and access.mgmt_access.site:
        _assert_site_scope(site_id, access.mgmt_access.site.id)

    site_result = await db.execute(select(Site).where(Site.id == site_id))
    site = site_result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")

    layouts = await menu_builder_service.get_published_menu_layouts_for_site(db, site)
    return [_to_detail(data) for data in layouts]
