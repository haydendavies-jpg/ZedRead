"""SQLAlchemy ORM model for table occupancy sessions (Android POS Phase 4)."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.table_map import TABLE_SESSION_STATUSES
from app.database import Base


class TableSession(Base):
    """
    One occupancy of a DiningTable — created when a table is seated, closed
    when it's cleared.

    status is one of README-tables-floormap.md's four statuses minus 'open':
    'seated' | 'ordered' | 'bill'. There is no stored 'open' status value —
    an unoccupied table simply has no TableSession row with
    DiningTable.active_session_id pointing at it (see DiningTable's class
    docstring). This keeps the status column's valid values exactly the set
    of states a *session* can be in, rather than overloading it with a
    "no session" pseudo-state.

    closed_at is NULL while the session is the table's active_session_id;
    clearing sets closed_at and detaches DiningTable.active_session_id back
    to NULL, but the TableSession row itself is kept — a new seating creates
    a brand new row rather than reopening this one, so occupancy history
    (README's timers, and any invoice attached via Invoice.table_session_id)
    survives across turns of the table.

    seated_at is the "activated" timer's start; last_touch_at advances on
    order/bill actions (README's "touch" timer — last order/bill action).

    merge_partner_session_id is a bidirectional link (README's `merges` map):
    table_session_service.merge_table_sessions sets it symmetrically on both
    sessions in the same transaction so either row resolves its partner.
    clear_table_session unlinks both sides if either half of a merged pair
    is cleared.

    client_ref/checksum mirror RegisterSession/Invoice's offline-sync
    idempotency + integrity pattern (app.utils.checksum) — set only on the
    SEAT call (the one write that creates this row); the mutation routes
    that transition an existing session don't need their own client_ref
    since they're addressed by this row's own id, which is itself already
    idempotent once created (a retried order/bill call against an
    already-'ordered'/'bill' session is a harmless no-op, not a duplicate
    write).
    """

    __tablename__ = "table_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in sorted(TABLE_SESSION_STATUSES)) + ")",
            name="ck_table_sessions_status_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    dining_table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dining_tables.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The table this occupancy belongs to",
    )
    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="seated",
        comment="'seated' | 'ordered' | 'bill' — see class docstring for why there is no 'open' value",
    )
    covers: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Number of guests seated at this table for this occupancy",
    )
    seated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When this occupancy began — the README's 'activated' timer start",
    )
    last_touch_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Most recent order/bill action — the README's 'touch' timer",
    )
    server_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="POS user serving this table; SET NULL if the user is later deleted",
    )
    merge_partner_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("table_sessions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
        comment="Bidirectional merge link — see class docstring",
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Set when the table is cleared; NULL while this is the table's active session",
    )
    client_ref: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
        comment="Client-generated idempotency key for the SEAT call that created this session",
    )
    checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 hex digest over this session's canonical seat payload (app.utils.checksum)",
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
