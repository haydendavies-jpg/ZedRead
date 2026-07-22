"""SQLAlchemy ORM model for the live-status half of a seatable table (Android POS Phase 4)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DiningTable(Base):
    """
    The queryable "this table exists and has live status" entity — a 1:1
    companion to a seatable-kind TableMapShape (stool/round/rect).

    Split deliberately from TableMapShape per the build plan's "authored on
    portal, device only renders" split: TableMapShape is pure layout
    (position/size/colour, edited by the portal editor), DiningTable is pure
    live state (which session currently occupies it, or none). A decorative
    shape (zone/bar-counter/entrance/wall) never gets a DiningTable row.

    active_session_id is NULL for an unoccupied ("open") table — there is no
    stored "open" status value on TableSession itself; open-ness is the
    absence of an active session (see TableSession's class docstring).
    Closing/clearing a session sets this back to NULL rather than deleting
    the TableSession row, so occupancy history survives (README's timers/
    audit trail) — see table_session_service.clear_table_session.

    reserved_at/reservation_label hold a future booking for an otherwise-open
    table (README's "◷ 7:30 · Chen" badge) — reservation is a property of
    the physical table waiting for its next occupancy, not of any particular
    TableSession row, so it lives here rather than on TableSession.
    """

    __tablename__ = "dining_tables"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    table_map_shape_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("table_map_shapes.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="The seatable shape this live-status row belongs to — 1:1, cascades on shape deletion",
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Denormalized from the parent map's site for simpler POS/portal site-scoped queries",
    )
    active_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("table_sessions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
        index=True,
        comment="The currently-open TableSession occupying this table, or NULL when the table is open",
    )
    reserved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Booking time for a future reservation on this (currently open) table",
    )
    reservation_label: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Free-text reservation badge, e.g. '7:30 · Chen'",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
