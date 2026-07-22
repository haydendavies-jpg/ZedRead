"""
Business logic for live table occupancy status (Android POS Phase 4).

Covers the POS read contract (GET /pos/table-map) and the status-mutation
routes: seat, order, bill, merge, clear, and reserve. Authoring (map/shape
CRUD, publish) lives in table_map_service — this module only ever touches
DiningTable/TableSession rows, never TableMap/TableMapShape.
"""

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    DINING_TABLE_RESERVED,
    TABLE_SESSION_BILLED,
    TABLE_SESSION_CLEARED,
    TABLE_SESSION_MERGED,
    TABLE_SESSION_ORDERED,
    TABLE_SESSION_SEATED,
)
from app.constants.statuses import ActorType
from app.models.dining_table import DiningTable
from app.models.site import Site
from app.models.table_map import TableMap
from app.models.table_map_shape import TableMapShape
from app.models.table_session import TableSession
from app.models.user import User
from app.schemas.table_map import PosDiningTableStatus, PosTableMapDetail, SeatTableRequest
from app.services.audit_service import log_action
from app.utils.checksum import verify_checksum

log = structlog.get_logger(__name__)


# ── Fetch helpers ─────────────────────────────────────────────────────────────


async def _get_dining_table_or_404(db: AsyncSession, site_id: uuid.UUID, dining_table_id: uuid.UUID) -> DiningTable:
    """Fetch a DiningTable by id scoped to a site, or raise HTTP 404."""
    result = await db.execute(
        select(DiningTable).where(DiningTable.id == dining_table_id, DiningTable.site_id == site_id)
    )
    dining_table = result.scalar_one_or_none()
    if dining_table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    return dining_table


async def _get_session_or_404(db: AsyncSession, site_id: uuid.UUID, session_id: uuid.UUID) -> TableSession:
    """Fetch a TableSession by id, scoped to a site via its DiningTable, or raise HTTP 404."""
    result = await db.execute(
        select(TableSession)
        .join(DiningTable, DiningTable.id == TableSession.dining_table_id)
        .where(TableSession.id == session_id, DiningTable.site_id == site_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table session not found")
    return session


async def _get_by_client_ref(db: AsyncSession, client_ref: str) -> TableSession | None:
    """Look up a table session previously created with this idempotency key."""
    result = await db.execute(select(TableSession).where(TableSession.client_ref == client_ref))
    return result.scalar_one_or_none()


# ── Status mutations ──────────────────────────────────────────────────────────


async def seat_table(
    db: AsyncSession, site_id: uuid.UUID, dining_table_id: uuid.UUID, payload: SeatTableRequest, actor: User
) -> TableSession:
    """
    Seat a table — opens a new TableSession and attaches it as the table's active session.

    Idempotent when payload.client_ref is supplied: a retried seat call that
    already landed returns the original session instead of raising 409 for a
    table that now looks already-occupied.

    Args:
        db: Active database session.
        site_id: The caller's POS site — the table must belong to it.
        dining_table_id: The table being seated.
        payload: Covers, optional server assignment, idempotency key, and checksum.
        actor: The authenticated POS user seating the table.

    Returns:
        TableSession: The newly created (or, on a deduped retry, the
            already-existing) session.

    Raises:
        HTTPException: 404 if the table doesn't exist at this site.
        HTTPException: 409 if the table already has an active session.
        HTTPException: 422 if payload.checksum is supplied and doesn't match.
    """
    if payload.client_ref is not None:
        existing = await _get_by_client_ref(db, payload.client_ref)
        if existing is not None:
            log.info("table_session.seat.deduped", client_ref=payload.client_ref)
            return existing

    dining_table = await _get_dining_table_or_404(db, site_id, dining_table_id)
    if dining_table.active_session_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Table already has an active session")

    now = datetime.now(timezone.utc)
    checksum = verify_checksum(
        {
            "dining_table_id": str(dining_table_id),
            "covers": payload.covers,
            "server_user_id": str(payload.server_user_id) if payload.server_user_id else None,
        },
        payload.checksum,
    )

    session = TableSession(
        id=uuid.uuid4(),
        dining_table_id=dining_table.id,
        status="seated",
        covers=payload.covers,
        seated_at=now,
        last_touch_at=now,
        server_user_id=payload.server_user_id,
        client_ref=payload.client_ref,
        checksum=checksum,
    )
    db.add(session)
    await db.flush()

    # Attach as the table's active session and clear any pending reservation
    # this seating fulfils
    dining_table.active_session_id = session.id
    dining_table.reserved_at = None
    dining_table.reservation_label = None

    await log_action(
        db=db,
        action=TABLE_SESSION_SEATED,
        entity_type="table_session",
        entity_id=str(session.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"dining_table_id": str(dining_table_id), "covers": payload.covers},
    )
    await db.commit()
    await db.refresh(session)
    log.info("table_session.seated", session_id=str(session.id), dining_table_id=str(dining_table_id))
    return session


async def mark_table_ordered(
    db: AsyncSession, site_id: uuid.UUID, session_id: uuid.UUID, checksum_in: str | None, actor: User
) -> TableSession:
    """
    Mark a seated table's session as ordered.

    Idempotent by nature: calling this again on an already-'ordered' session
    is a harmless no-op (still bumps last_touch_at) rather than an error —
    the mutation is addressed by session_id, which only exists once created.

    Raises:
        HTTPException: 404 if the session doesn't exist at this site.
        HTTPException: 400 if the session is already closed.
        HTTPException: 422 if checksum_in is supplied and doesn't match.
    """
    session = await _get_session_or_404(db, site_id, session_id)
    if session.closed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Table session is already cleared")

    verify_checksum({"session_id": str(session_id), "transition": "ordered"}, checksum_in)

    before_status = session.status
    session.status = "ordered"
    session.last_touch_at = datetime.now(timezone.utc)

    await log_action(
        db=db,
        action=TABLE_SESSION_ORDERED,
        entity_type="table_session",
        entity_id=str(session.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"status": before_status},
        after_state={"status": "ordered"},
    )
    await db.commit()
    await db.refresh(session)
    return session


async def mark_table_bill(
    db: AsyncSession, site_id: uuid.UUID, session_id: uuid.UUID, checksum_in: str | None, actor: User
) -> TableSession:
    """
    Mark a table's session as needing its bill.

    Raises:
        HTTPException: 404 if the session doesn't exist at this site.
        HTTPException: 400 if the session is already closed.
        HTTPException: 422 if checksum_in is supplied and doesn't match.
    """
    session = await _get_session_or_404(db, site_id, session_id)
    if session.closed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Table session is already cleared")

    verify_checksum({"session_id": str(session_id), "transition": "bill"}, checksum_in)

    before_status = session.status
    session.status = "bill"
    session.last_touch_at = datetime.now(timezone.utc)

    await log_action(
        db=db,
        action=TABLE_SESSION_BILLED,
        entity_type="table_session",
        entity_id=str(session.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"status": before_status},
        after_state={"status": "bill"},
    )
    await db.commit()
    await db.refresh(session)
    return session


async def merge_table_sessions(
    db: AsyncSession, site_id: uuid.UUID, session_id: uuid.UUID, partner_session_id: uuid.UUID, checksum_in: str | None, actor: User
) -> TableSession:
    """
    Bidirectionally merge two open table sessions (README's `merges` map).

    Sets merge_partner_session_id on both rows in the same transaction so
    either table's status resolves its partner. Rejects merging a session
    that is already merged — clear (or a future unmerge) must run first.

    Raises:
        HTTPException: 404 if either session doesn't exist at this site.
        HTTPException: 400 if either session is closed, already merged, or
            partner_session_id equals session_id.
        HTTPException: 422 if checksum_in is supplied and doesn't match.
    """
    if session_id == partner_session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot merge a table session with itself")

    session = await _get_session_or_404(db, site_id, session_id)
    partner = await _get_session_or_404(db, site_id, partner_session_id)

    if session.closed_at is not None or partner.closed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot merge a cleared table session")
    if session.merge_partner_session_id is not None or partner.merge_partner_session_id is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One of these tables is already merged")

    verify_checksum({"session_id": str(session_id), "partner_session_id": str(partner_session_id)}, checksum_in)

    session.merge_partner_session_id = partner.id
    partner.merge_partner_session_id = session.id

    await log_action(
        db=db,
        action=TABLE_SESSION_MERGED,
        entity_type="table_session",
        entity_id=str(session.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"session_id": str(session_id), "partner_session_id": str(partner_session_id)},
    )
    await db.commit()
    await db.refresh(session)
    log.info("table_session.merged", session_id=str(session_id), partner_session_id=str(partner_session_id))
    return session


async def clear_table_session(
    db: AsyncSession, site_id: uuid.UUID, session_id: uuid.UUID, checksum_in: str | None, actor: User
) -> TableSession:
    """
    Clear a table — closes its session, unlinks any merge partner, and returns the table to 'open'.

    Idempotent by nature: clearing an already-closed session returns it
    unchanged rather than erroring, since a retried clear call has nothing
    left to do.

    Raises:
        HTTPException: 404 if the session doesn't exist at this site.
        HTTPException: 422 if checksum_in is supplied and doesn't match.
    """
    session = await _get_session_or_404(db, site_id, session_id)
    if session.closed_at is not None:
        log.info("table_session.clear.deduped", session_id=str(session_id))
        return session

    verify_checksum({"session_id": str(session_id), "transition": "clear"}, checksum_in)

    now = datetime.now(timezone.utc)
    session.closed_at = now

    # Unlink a merge partner, if any — the partner's own session stays open,
    # only the merge link (and this table's occupancy) ends
    if session.merge_partner_session_id is not None:
        partner_result = await db.execute(select(TableSession).where(TableSession.id == session.merge_partner_session_id))
        partner = partner_result.scalar_one_or_none()
        if partner is not None:
            partner.merge_partner_session_id = None
        session.merge_partner_session_id = None

    # Detach from the table so it reads as 'open' again
    table_result = await db.execute(select(DiningTable).where(DiningTable.active_session_id == session.id))
    dining_table = table_result.scalar_one_or_none()
    if dining_table is not None:
        dining_table.active_session_id = None

    await log_action(
        db=db,
        action=TABLE_SESSION_CLEARED,
        entity_type="table_session",
        entity_id=str(session.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"status": session.status},
        after_state={"closed_at": now.isoformat()},
    )
    await db.commit()
    await db.refresh(session)
    log.info("table_session.cleared", session_id=str(session_id))
    return session


async def reserve_dining_table(
    db: AsyncSession,
    site_id: uuid.UUID,
    dining_table_id: uuid.UUID,
    reservation_label: str,
    reserved_at: datetime,
    actor: User,
) -> DiningTable:
    """
    Record a future reservation on a currently-open table.

    Raises:
        HTTPException: 404 if the table doesn't exist at this site.
        HTTPException: 400 if the table currently has an active session.
    """
    dining_table = await _get_dining_table_or_404(db, site_id, dining_table_id)
    if dining_table.active_session_id is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot reserve a table that is currently occupied")

    dining_table.reserved_at = reserved_at
    dining_table.reservation_label = reservation_label

    await log_action(
        db=db,
        action=DINING_TABLE_RESERVED,
        entity_type="dining_table",
        entity_id=str(dining_table.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"reservation_label": reservation_label, "reserved_at": reserved_at.isoformat()},
    )
    await db.commit()
    await db.refresh(dining_table)
    return dining_table


# ── POS consumption contract ──────────────────────────────────────────────────


async def get_published_table_maps_for_site(db: AsyncSession, site: Site) -> list[PosTableMapDetail]:
    """
    Fetch every published table map for a site, each shape carrying live status where applicable.

    This is the read-only contract Android consumes via
    GET /pos/table-map?site_id= to render the floor plan.

    Args:
        db: Active database session.
        site: The site to resolve published table maps for.

    Returns:
        list[PosTableMapDetail]: Published maps ordered by sort_order, each
            with every shape — table-kind shapes carry the joined
            DiningTable/TableSession live status, decorative shapes don't.
    """
    maps_result = await db.execute(
        select(TableMap)
        .where(TableMap.site_id == site.id, TableMap.is_published.is_(True), TableMap.is_active.is_(True))
        .order_by(TableMap.sort_order)
    )
    table_maps = list(maps_result.scalars().all())
    if not table_maps:
        return []

    map_ids = [m.id for m in table_maps]
    shapes_result = await db.execute(
        select(TableMapShape).where(TableMapShape.table_map_id.in_(map_ids)).order_by(TableMapShape.sort_order)
    )
    shapes = list(shapes_result.scalars().all())
    shape_ids = [s.id for s in shapes]

    # One joined query resolves every table-kind shape's live status —
    # DiningTable LEFT JOIN TableSession (only the currently-active one) LEFT
    # JOIN User (server name) — decorative shapes simply have no DiningTable row.
    status_result = await db.execute(
        select(DiningTable, TableSession, User)
        .outerjoin(TableSession, TableSession.id == DiningTable.active_session_id)
        .outerjoin(User, User.id == TableSession.server_user_id)
        .where(DiningTable.table_map_shape_id.in_(shape_ids))
    )
    status_by_shape_id: dict[uuid.UUID, tuple[DiningTable, TableSession | None, User | None]] = {
        dining_table.table_map_shape_id: (dining_table, session, server)
        for dining_table, session, server in status_result.all()
    }

    # Merge partners' table labels are resolved separately: a merged
    # session's partner belongs to a *different* shape than the one being
    # rendered, so it isn't in status_by_shape_id's per-shape join above.
    partner_session_ids = {
        session.merge_partner_session_id
        for _, session, _ in status_by_shape_id.values()
        if session and session.merge_partner_session_id
    }
    partner_labels: dict[uuid.UUID, str] = {}
    if partner_session_ids:
        partner_result = await db.execute(
            select(TableSession.id, TableMapShape.label)
            .join(DiningTable, DiningTable.id == TableSession.dining_table_id)
            .join(TableMapShape, TableMapShape.id == DiningTable.table_map_shape_id)
            .where(TableSession.id.in_(partner_session_ids))
        )
        partner_labels = dict(partner_result.all())

    shapes_by_map: dict[uuid.UUID, list[PosDiningTableStatus]] = {}
    for shape in shapes:
        dining_table, session, server = status_by_shape_id.get(shape.id, (None, None, None))
        shapes_by_map.setdefault(shape.table_map_id, []).append(
            PosDiningTableStatus(
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
                dining_table_id=dining_table.id if dining_table else None,
                status=session.status if session else None,
                session_id=session.id if session else None,
                covers=session.covers if session else None,
                seated_at=session.seated_at if session else None,
                last_touch_at=session.last_touch_at if session else None,
                server_user_id=session.server_user_id if session else None,
                server_name=server.name if server else None,
                merge_partner_session_id=session.merge_partner_session_id if session else None,
                merge_partner_label=partner_labels.get(session.merge_partner_session_id) if session and session.merge_partner_session_id else None,
                reserved_at=dining_table.reserved_at if dining_table else None,
                reservation_label=dining_table.reservation_label if dining_table else None,
            )
        )

    return [
        PosTableMapDetail(
            id=table_map.id,
            brand_id=table_map.brand_id,
            site_id=table_map.site_id,
            name=table_map.name,
            sort_order=table_map.sort_order,
            is_published=table_map.is_published,
            published_at=table_map.published_at,
            grid_size=table_map.grid_size,
            is_grid_locked=table_map.is_grid_locked,
            is_active=table_map.is_active,
            shape_count=len(shapes_by_map.get(table_map.id, [])),
            created_at=table_map.created_at,
            updated_at=table_map.updated_at,
            shapes=shapes_by_map.get(table_map.id, []),
        )
        for table_map in table_maps
    ]
