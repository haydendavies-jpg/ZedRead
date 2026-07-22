"""
Business logic for authoring table maps & their shapes (Android POS Phase 4).

A TableMap is a named floor plan for one site; a TableMapShape is a single
placed element on it — either a seatable table (kind in TABLE_SHAPE_KINDS,
gets a 1:1 DiningTable row for live status) or a decorative backdrop element
(kind in DECOR_SHAPE_KINDS — zones, bar counter, entrance, walls). This
module owns authoring-time CRUD/publish/duplicate; live occupancy status
(seat/order/bill/merge/clear) lives in table_session_service.
"""

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    TABLE_MAP_CREATED,
    TABLE_MAP_DELETED,
    TABLE_MAP_DUPLICATED,
    TABLE_MAP_PUBLISHED,
    TABLE_MAP_SHAPE_ADDED,
    TABLE_MAP_SHAPE_REMOVED,
    TABLE_MAP_SHAPE_UPDATED,
    TABLE_MAP_UNPUBLISHED,
    TABLE_MAP_UPDATED,
)
from app.constants.table_map import TABLE_SHAPE_KINDS
from app.models.dining_table import DiningTable
from app.models.site import Site
from app.models.table_map import TableMap
from app.models.table_map_shape import TableMapShape
from app.models.user import User
from app.schemas.table_map import TableMapCreate, TableMapShapeCreate, TableMapShapeUpdate, TableMapUpdate
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


# ── Fetch helpers ─────────────────────────────────────────────────────────────


async def _get_map_or_404(db: AsyncSession, brand_id: uuid.UUID, table_map_id: uuid.UUID) -> TableMap:
    """Fetch a TableMap by id scoped to a brand, or raise HTTP 404."""
    result = await db.execute(
        select(TableMap).where(TableMap.id == table_map_id, TableMap.brand_id == brand_id)
    )
    table_map = result.scalar_one_or_none()
    if table_map is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table map not found")
    return table_map


async def _get_shape_or_404(db: AsyncSession, table_map_id: uuid.UUID, shape_id: uuid.UUID) -> TableMapShape:
    """Fetch a TableMapShape by id scoped to a map, or raise HTTP 404."""
    result = await db.execute(
        select(TableMapShape).where(TableMapShape.id == shape_id, TableMapShape.table_map_id == table_map_id)
    )
    shape = result.scalar_one_or_none()
    if shape is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table map shape not found")
    return shape


async def _validate_site(db: AsyncSession, brand_id: uuid.UUID, site_id: uuid.UUID) -> Site:
    """Raise 400 if site_id does not belong to brand_id; otherwise return the Site."""
    result = await db.execute(select(Site).where(Site.id == site_id, Site.brand_id == brand_id))
    site = result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="site_id does not belong to this brand")
    return site


async def _load_shapes(db: AsyncSession, table_map_id: uuid.UUID) -> list[TableMapShape]:
    """Load every shape on a map, ordered by sort_order."""
    result = await db.execute(
        select(TableMapShape).where(TableMapShape.table_map_id == table_map_id).order_by(TableMapShape.sort_order)
    )
    return list(result.scalars().all())


async def _dining_table_ids_by_shape(db: AsyncSession, shape_ids: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
    """Map each table-kind shape id to its 1:1 DiningTable id, for shape response payloads."""
    if not shape_ids:
        return {}
    result = await db.execute(
        select(DiningTable.table_map_shape_id, DiningTable.id).where(DiningTable.table_map_shape_id.in_(shape_ids))
    )
    return dict(result.all())


# ── Map CRUD ──────────────────────────────────────────────────────────────────


async def list_table_maps(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 200,
) -> list[tuple[TableMap, int]]:
    """
    List active table maps for a brand, optionally filtered to one site.

    Args:
        db: Active database session.
        brand_id: UUID of the brand to list maps for.
        site_id: If given, only include maps for this site.
        skip: Pagination offset.
        limit: Maximum number of maps to return.

    Returns:
        list[tuple[TableMap, int]]: Maps ordered by sort_order, each paired
            with its total shape count for the list view's caption.
    """
    shape_count_subq = (
        select(func.count(TableMapShape.id))
        .where(TableMapShape.table_map_id == TableMap.id)
        .correlate(TableMap)
        .scalar_subquery()
    )
    query = select(TableMap, shape_count_subq).where(TableMap.brand_id == brand_id, TableMap.is_active.is_(True))
    if site_id is not None:
        query = query.where(TableMap.site_id == site_id)
    query = query.order_by(TableMap.sort_order).offset(skip).limit(limit)
    result = await db.execute(query)
    return [(table_map, count) for table_map, count in result.all()]


async def get_table_map_detail(db: AsyncSession, brand_id: uuid.UUID, table_map_id: uuid.UUID) -> dict:
    """
    Fetch a table map with its shapes.

    Returns:
        dict: Keys 'map' (TableMap) and 'shapes' (list[tuple[TableMapShape, dining_table_id | None]]).

    Raises:
        HTTPException: 404 if not found.
    """
    table_map = await _get_map_or_404(db, brand_id, table_map_id)
    shapes = await _load_shapes(db, table_map_id)
    dining_table_ids = await _dining_table_ids_by_shape(db, [s.id for s in shapes])
    return {
        "map": table_map,
        "shapes": [(shape, dining_table_ids.get(shape.id)) for shape in shapes],
    }


async def create_table_map(db: AsyncSession, brand_id: uuid.UUID, payload: TableMapCreate, actor: User) -> TableMap:
    """
    Create a new table map for a site.

    Raises:
        HTTPException: 400 if site_id does not belong to brand_id.
    """
    await _validate_site(db, brand_id, payload.site_id)

    table_map = TableMap(
        id=uuid.uuid4(),
        brand_id=brand_id,
        site_id=payload.site_id,
        name=payload.name,
        sort_order=payload.sort_order,
        grid_size=payload.grid_size,
        is_grid_locked=payload.is_grid_locked,
        is_published=False,
    )
    db.add(table_map)
    await db.flush()

    await log_action(
        db=db,
        action=TABLE_MAP_CREATED,
        entity_type="table_map",
        entity_id=str(table_map.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"name": table_map.name, "site_id": str(payload.site_id)},
    )
    await db.commit()
    await db.refresh(table_map)
    log.info("table_map.created", table_map_id=str(table_map.id), site_id=str(payload.site_id))
    return table_map


async def update_table_map(
    db: AsyncSession, brand_id: uuid.UUID, table_map_id: uuid.UUID, payload: TableMapUpdate, actor: User
) -> TableMap:
    """Update a table map's mutable fields (name/sort_order/grid settings)."""
    table_map = await _get_map_or_404(db, brand_id, table_map_id)

    before: dict = {}
    after: dict = {}
    for field in ("name", "sort_order", "grid_size", "is_grid_locked"):
        value = getattr(payload, field)
        if value is not None:
            before[field] = getattr(table_map, field)
            setattr(table_map, field, value)
            after[field] = value

    await log_action(
        db=db,
        action=TABLE_MAP_UPDATED,
        entity_type="table_map",
        entity_id=str(table_map.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after,
    )
    await db.commit()
    await db.refresh(table_map)
    return table_map


async def delete_table_map(db: AsyncSession, brand_id: uuid.UUID, table_map_id: uuid.UUID, actor: User) -> None:
    """
    Soft-delete a table map (is_active=False) — its shapes/dining tables are left in place.

    Soft delete rather than a hard delete (unlike menu_layouts) so any
    TableSession history attached to this map's tables is never orphaned by
    an authoring-time archive action. See TableMap's class docstring.
    """
    table_map = await _get_map_or_404(db, brand_id, table_map_id)
    table_map.is_active = False
    table_map.is_published = False

    await log_action(
        db=db,
        action=TABLE_MAP_DELETED,
        entity_type="table_map",
        entity_id=str(table_map.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": True},
        after_state={"is_active": False},
    )
    await db.commit()
    log.info("table_map.deleted", table_map_id=str(table_map_id))


async def duplicate_table_map(db: AsyncSession, brand_id: uuid.UUID, table_map_id: uuid.UUID, actor: User) -> TableMap:
    """
    Duplicate a map and its shapes (name suffixed "(copy)"), each table-kind shape getting a fresh DiningTable.

    The copy starts unpublished, with no live occupancy — a table map's
    shape tree is flat (no tabs/folders nesting like MenuLayout), so this is
    a single pass rather than duplicate_menu_layout's two-pass id remap.

    Raises:
        HTTPException: 404 if not found.
    """
    source = await _get_map_or_404(db, brand_id, table_map_id)
    source_shapes = await _load_shapes(db, table_map_id)

    new_map = TableMap(
        id=uuid.uuid4(),
        brand_id=brand_id,
        site_id=source.site_id,
        name=f"{source.name} (copy)",
        sort_order=source.sort_order,
        grid_size=source.grid_size,
        is_grid_locked=source.is_grid_locked,
        is_published=False,
    )
    db.add(new_map)
    await db.flush()

    for shape in source_shapes:
        new_shape = TableMapShape(
            id=uuid.uuid4(),
            table_map_id=new_map.id,
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
        )
        db.add(new_shape)
        if shape.kind in TABLE_SHAPE_KINDS:
            # The client-generated id is known ahead of the INSERT, but the
            # FK constraint is checked against the row's actual presence at
            # INSERT time — flush new_shape first so its row exists before
            # the dependent DiningTable insert executes (the two use_alter'd
            # FK constraints from migration 0056 aren't picked up by
            # SQLAlchemy's automatic dependency-sort between these tables).
            await db.flush()
            db.add(DiningTable(id=uuid.uuid4(), table_map_shape_id=new_shape.id, site_id=new_map.site_id))

    await log_action(
        db=db,
        action=TABLE_MAP_DUPLICATED,
        entity_type="table_map",
        entity_id=str(new_map.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"name": new_map.name, "duplicated_from": str(source.id)},
    )
    await db.commit()
    await db.refresh(new_map)
    return new_map


async def publish_table_map(db: AsyncSession, brand_id: uuid.UUID, table_map_id: uuid.UUID, actor: User) -> TableMap:
    """Publish a table map, making it visible to the POS read contract."""
    table_map = await _get_map_or_404(db, brand_id, table_map_id)
    table_map.is_published = True
    table_map.published_at = datetime.now(timezone.utc)

    await log_action(
        db=db,
        action=TABLE_MAP_PUBLISHED,
        entity_type="table_map",
        entity_id=str(table_map.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"is_published": True},
    )
    await db.commit()
    await db.refresh(table_map)
    log.info("table_map.published", table_map_id=str(table_map.id))
    return table_map


async def unpublish_table_map(db: AsyncSession, brand_id: uuid.UUID, table_map_id: uuid.UUID, actor: User) -> TableMap:
    """Unpublish a table map."""
    table_map = await _get_map_or_404(db, brand_id, table_map_id)
    table_map.is_published = False

    await log_action(
        db=db,
        action=TABLE_MAP_UNPUBLISHED,
        entity_type="table_map",
        entity_id=str(table_map.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"is_published": False},
    )
    await db.commit()
    await db.refresh(table_map)
    return table_map


# ── Shape CRUD ────────────────────────────────────────────────────────────────


async def create_table_map_shape(
    db: AsyncSession, brand_id: uuid.UUID, table_map_id: uuid.UUID, payload: TableMapShapeCreate, actor: User
) -> tuple[TableMapShape, uuid.UUID | None]:
    """
    Add a shape to a map. A table-kind shape (stool/round/rect) also creates its 1:1 DiningTable row.

    Returns:
        tuple[TableMapShape, uuid.UUID | None]: The created shape and its
            new DiningTable's id (None for a decorative shape).

    Raises:
        HTTPException: 404 if the map does not exist for this brand.
    """
    table_map = await _get_map_or_404(db, brand_id, table_map_id)

    shape = TableMapShape(
        id=uuid.uuid4(),
        table_map_id=table_map_id,
        kind=payload.kind,
        label=payload.label,
        x=payload.x,
        y=payload.y,
        w=payload.w,
        h=payload.h,
        color=payload.color,
        is_locked=payload.is_locked,
        dashed=payload.dashed,
        sort_order=payload.sort_order,
    )
    db.add(shape)
    await db.flush()

    dining_table_id: uuid.UUID | None = None
    if payload.kind in TABLE_SHAPE_KINDS:
        dining_table = DiningTable(id=uuid.uuid4(), table_map_shape_id=shape.id, site_id=table_map.site_id)
        db.add(dining_table)
        await db.flush()
        dining_table_id = dining_table.id

    await log_action(
        db=db,
        action=TABLE_MAP_SHAPE_ADDED,
        entity_type="table_map_shape",
        entity_id=str(shape.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"kind": shape.kind, "label": shape.label, "table_map_id": str(table_map_id)},
    )
    await db.commit()
    await db.refresh(shape)
    return shape, dining_table_id


async def update_table_map_shape(
    db: AsyncSession,
    brand_id: uuid.UUID,
    table_map_id: uuid.UUID,
    shape_id: uuid.UUID,
    payload: TableMapShapeUpdate,
    actor: User,
) -> tuple[TableMapShape, uuid.UUID | None]:
    """Reposition/resize/restyle a shape — every field optional. kind cannot be changed here."""
    await _get_map_or_404(db, brand_id, table_map_id)
    shape = await _get_shape_or_404(db, table_map_id, shape_id)

    before: dict = {}
    after: dict = {}
    for field in ("label", "x", "y", "w", "h", "color", "is_locked", "dashed", "sort_order"):
        value = getattr(payload, field)
        if value is not None:
            before[field] = getattr(shape, field)
            setattr(shape, field, value)
            after[field] = value

    await log_action(
        db=db,
        action=TABLE_MAP_SHAPE_UPDATED,
        entity_type="table_map_shape",
        entity_id=str(shape.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after,
    )
    await db.commit()
    await db.refresh(shape)

    dining_table_ids = await _dining_table_ids_by_shape(db, [shape.id])
    return shape, dining_table_ids.get(shape.id)


async def delete_table_map_shape(
    db: AsyncSession, brand_id: uuid.UUID, table_map_id: uuid.UUID, shape_id: uuid.UUID, actor: User
) -> None:
    """Remove a shape from a map. Its DiningTable (and any TableSession history) cascade-deletes too."""
    await _get_map_or_404(db, brand_id, table_map_id)
    shape = await _get_shape_or_404(db, table_map_id, shape_id)

    await log_action(
        db=db,
        action=TABLE_MAP_SHAPE_REMOVED,
        entity_type="table_map_shape",
        entity_id=str(shape.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"kind": shape.kind, "label": shape.label},
    )
    await db.delete(shape)
    await db.commit()
