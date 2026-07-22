"""
Table maps & floor service routes (Android POS Phase 4).

Management CRUD (author maps/shapes, publish/unpublish, duplicate) lives
under /table-maps (portal/management JWT only, mirroring
routes/menu_layouts.py's _require_management convention — POS terminal
tokens are read-only/status-only here). The POS read contract and live
status mutations (seat/order/bill/merge/clear/reserve) live under /pos,
using resolve_access directly (POSAccess always carries a site) the same
way routes/register_sessions.py and routes/invoices.py's write routes do.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.site import Site
from app.schemas.table_map import (
    ClearTableRequest,
    MergeTableRequest,
    OrderTableRequest,
    BillTableRequest,
    PosTableMapDetail,
    ReserveTableRequest,
    SeatTableRequest,
    TableMapCreate,
    TableMapDetail,
    TableMapOut,
    TableMapShapeCreate,
    TableMapShapeOut,
    TableMapShapeUpdate,
    TableMapUpdate,
    TableSessionOut,
)
from app.services import table_map_service, table_session_service
from app.services.report_service import _assert_site_scope
from app.utils.dependencies import CatalogAccess, POSAccess, resolve_access, resolve_catalog_access

router = APIRouter(prefix="/table-maps", tags=["table-maps"])
pos_router = APIRouter(prefix="/pos", tags=["pos"])


def _require_management(access: CatalogAccess) -> None:
    """
    Reject POS terminal tokens from table map authoring operations.

    Args:
        access: Resolved catalog access for the current request.

    Raises:
        HTTPException: 403 if the caller authenticated with a POS terminal JWT.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Table map authoring requires a management or portal JWT",
        )


def _to_shape_out(shape, dining_table_id: uuid.UUID | None) -> TableMapShapeOut:
    """Build a TableMapShapeOut from a (shape, dining_table_id) pair."""
    return TableMapShapeOut(
        id=shape.id,
        table_map_id=shape.table_map_id,
        kind=shape.kind,
        label=shape.label,
        x=shape.x,
        y=shape.y,
        w=shape.w,
        h=shape.h,
        color=shape.color,
        is_locked=shape.is_locked,
        dashed=shape.dashed,
        sort_order=shape.sort_order,
        dining_table_id=dining_table_id,
    )


def _to_detail(data: dict) -> TableMapDetail:
    """Build a TableMapDetail response from the service's {'map', 'shapes'} dict."""
    base = TableMapOut.model_validate(data["map"]).model_dump()
    base["shape_count"] = len(data["shapes"])
    return TableMapDetail(**base, shapes=[_to_shape_out(shape, dt_id) for shape, dt_id in data["shapes"]])


# ── Maps ──────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[TableMapOut], status_code=status.HTTP_200_OK)
async def list_table_maps(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    site_id: uuid.UUID | None = Query(None, description="Filter to maps for this site"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[TableMapOut]:
    """List active table maps for the authenticated user's brand, each with its shape count."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    rows = await table_map_service.list_table_maps(db, effective_brand_id, site_id, skip, limit)
    results = []
    for table_map, count in rows:
        out = TableMapOut.model_validate(table_map)
        out.shape_count = count
        results.append(out)
    return results


@router.post("", response_model=TableMapOut, status_code=status.HTTP_201_CREATED)
async def create_table_map(
    payload: TableMapCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> TableMapOut:
    """Create a new table map for a site."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    table_map = await table_map_service.create_table_map(db, effective_brand_id, payload, access.actor_user)
    return TableMapOut.model_validate(table_map)


@router.get("/{table_map_id}", response_model=TableMapDetail, status_code=status.HTTP_200_OK)
async def get_table_map(
    table_map_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> TableMapDetail:
    """Fetch a table map with its full set of shapes."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    data = await table_map_service.get_table_map_detail(db, effective_brand_id, table_map_id)
    return _to_detail(data)


@router.patch("/{table_map_id}", response_model=TableMapOut, status_code=status.HTTP_200_OK)
async def update_table_map(
    table_map_id: uuid.UUID,
    payload: TableMapUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> TableMapOut:
    """Update a table map's mutable fields (name/sort_order/grid settings)."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    table_map = await table_map_service.update_table_map(db, effective_brand_id, table_map_id, payload, access.actor_user)
    return TableMapOut.model_validate(table_map)


@router.delete("/{table_map_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def delete_table_map(
    table_map_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete (archive) a table map."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    await table_map_service.delete_table_map(db, effective_brand_id, table_map_id, access.actor_user)


@router.post("/{table_map_id}/duplicate", response_model=TableMapOut, status_code=status.HTTP_201_CREATED)
async def duplicate_table_map(
    table_map_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> TableMapOut:
    """Duplicate a map and its shapes. The copy starts unpublished with fresh (unoccupied) tables."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    table_map = await table_map_service.duplicate_table_map(db, effective_brand_id, table_map_id, access.actor_user)
    return TableMapOut.model_validate(table_map)


@router.post("/{table_map_id}/publish", response_model=TableMapOut, status_code=status.HTTP_200_OK)
async def publish_table_map(
    table_map_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> TableMapOut:
    """Publish a table map, making it visible to the POS read contract."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    table_map = await table_map_service.publish_table_map(db, effective_brand_id, table_map_id, access.actor_user)
    return TableMapOut.model_validate(table_map)


@router.post("/{table_map_id}/unpublish", response_model=TableMapOut, status_code=status.HTTP_200_OK)
async def unpublish_table_map(
    table_map_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> TableMapOut:
    """Unpublish a table map."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    table_map = await table_map_service.unpublish_table_map(db, effective_brand_id, table_map_id, access.actor_user)
    return TableMapOut.model_validate(table_map)


# ── Shapes ────────────────────────────────────────────────────────────────────


@router.post("/{table_map_id}/shapes", response_model=TableMapShapeOut, status_code=status.HTTP_201_CREATED)
async def create_table_map_shape(
    table_map_id: uuid.UUID,
    payload: TableMapShapeCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> TableMapShapeOut:
    """Add a shape to a map — a table-kind shape also creates its live-status DiningTable row."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    shape, dining_table_id = await table_map_service.create_table_map_shape(
        db, effective_brand_id, table_map_id, payload, access.actor_user
    )
    return _to_shape_out(shape, dining_table_id)


@router.patch(
    "/{table_map_id}/shapes/{shape_id}", response_model=TableMapShapeOut, status_code=status.HTTP_200_OK
)
async def update_table_map_shape(
    table_map_id: uuid.UUID,
    shape_id: uuid.UUID,
    payload: TableMapShapeUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> TableMapShapeOut:
    """Reposition/resize/restyle a shape (the editor's drag/resize/inspector actions)."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    shape, dining_table_id = await table_map_service.update_table_map_shape(
        db, effective_brand_id, table_map_id, shape_id, payload, access.actor_user
    )
    return _to_shape_out(shape, dining_table_id)


@router.delete(
    "/{table_map_id}/shapes/{shape_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT
)
async def delete_table_map_shape(
    table_map_id: uuid.UUID,
    shape_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a shape from a map — its DiningTable (and any TableSession history) cascade-deletes too."""
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    await table_map_service.delete_table_map_shape(db, effective_brand_id, table_map_id, shape_id, access.actor_user)


# ── POS consumption contract ──────────────────────────────────────────────────


@pos_router.get("/table-map", response_model=list[PosTableMapDetail], status_code=status.HTTP_200_OK)
async def get_pos_table_map(
    site_id: uuid.UUID = Query(..., description="Site to resolve published table maps for"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[PosTableMapDetail]:
    """
    Publish contract for the Android app: every published table map for a site, with live status.

    Mirrors GET /pos/menu-layout's auth/shape convention — accepts either a
    POS terminal token (site-scoped to its own token) or a management token
    scoped to this site.
    """
    if access.pos_access:
        _assert_site_scope(site_id, access.pos_access.site.id)
    elif access.mgmt_access and access.mgmt_access.scope == "site" and access.mgmt_access.site:
        _assert_site_scope(site_id, access.mgmt_access.site.id)

    site_result = await db.execute(select(Site).where(Site.id == site_id))
    site = site_result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")

    return await table_session_service.get_published_table_maps_for_site(db, site)


# ── Live status mutations ───────────────────────────────────────────────────


@pos_router.post(
    "/dining-tables/{dining_table_id}/seat", response_model=TableSessionOut, status_code=status.HTTP_201_CREATED
)
async def seat_table(
    dining_table_id: uuid.UUID,
    payload: SeatTableRequest,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> TableSessionOut:
    """Seat a table — opens a new occupancy session. Idempotent via payload.client_ref."""
    session = await table_session_service.seat_table(db, access.site.id, dining_table_id, payload, access.user)
    return TableSessionOut.model_validate(session)


@pos_router.post(
    "/dining-tables/{dining_table_id}/reserve", response_model=None, status_code=status.HTTP_200_OK
)
async def reserve_table(
    dining_table_id: uuid.UUID,
    payload: ReserveTableRequest,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Record a future reservation on a currently-open table."""
    await table_session_service.reserve_dining_table(
        db, access.site.id, dining_table_id, payload.reservation_label, payload.reserved_at, access.user
    )


@pos_router.post(
    "/table-sessions/{session_id}/order", response_model=TableSessionOut, status_code=status.HTTP_200_OK
)
async def mark_table_ordered(
    session_id: uuid.UUID,
    payload: OrderTableRequest,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> TableSessionOut:
    """Mark a seated table's session as ordered."""
    session = await table_session_service.mark_table_ordered(db, access.site.id, session_id, payload.checksum, access.user)
    return TableSessionOut.model_validate(session)


@pos_router.post(
    "/table-sessions/{session_id}/bill", response_model=TableSessionOut, status_code=status.HTTP_200_OK
)
async def mark_table_bill(
    session_id: uuid.UUID,
    payload: BillTableRequest,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> TableSessionOut:
    """Mark a table's session as needing its bill."""
    session = await table_session_service.mark_table_bill(db, access.site.id, session_id, payload.checksum, access.user)
    return TableSessionOut.model_validate(session)


@pos_router.post(
    "/table-sessions/{session_id}/merge", response_model=TableSessionOut, status_code=status.HTTP_200_OK
)
async def merge_table_sessions(
    session_id: uuid.UUID,
    payload: MergeTableRequest,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> TableSessionOut:
    """Bidirectionally merge two open table sessions."""
    session = await table_session_service.merge_table_sessions(
        db, access.site.id, session_id, payload.partner_session_id, payload.checksum, access.user
    )
    return TableSessionOut.model_validate(session)


@pos_router.post(
    "/table-sessions/{session_id}/clear", response_model=TableSessionOut, status_code=status.HTTP_200_OK
)
async def clear_table_session(
    session_id: uuid.UUID,
    payload: ClearTableRequest,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> TableSessionOut:
    """Clear a table — closes its session and returns the table to 'open'. Idempotent."""
    session = await table_session_service.clear_table_session(db, access.site.id, session_id, payload.checksum, access.user)
    return TableSessionOut.model_validate(session)
