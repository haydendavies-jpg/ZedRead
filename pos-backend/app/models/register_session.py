"""SQLAlchemy ORM model for POS register (till) sessions."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RegisterSession(Base):
    """
    A cash-accountability shift for one POS terminal (PosDevice).

    Opened when staff enter start-of-day cash and closed when they cash up at
    the end of the day. Scoped per-device (not per-site) — two terminals at
    one site run independent sessions. Invoices raised while a session is
    open reference it via Invoice.register_session_id; invoice creation is
    rejected while no open session exists for the device (see
    register_session_service.get_open_session_or_404()).

    opened_at/closed_at are supplied by the device (its own local clock, per
    the product requirement that a cash-up is recorded against the device's
    time) rather than defaulted server-side — created_at/updated_at below are
    the separate server-side bookkeeping timestamps.

    Only one session may be open per device at a time, enforced by a partial
    unique index (see migration) rather than an application-level race-prone
    check alone.
    """

    __tablename__ = "register_sessions"
    __table_args__ = (
        Index(
            "uq_register_sessions_one_open_per_device",
            "device_id",
            unique=True,
            postgresql_where="status = 'open'",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pos_devices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="The terminal this session belongs to — sessions are per-device, not per-site",
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Denormalized from the device for simpler site-scoped portal reporting queries",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        comment="Lifecycle state — open | closed",
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Device-local timestamp the session was opened — supplied by the client, not server time",
    )
    opening_cash_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Cash counted into the till at the start of the shift",
    )
    opened_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="POS user who opened the session; SET NULL if the user is later deleted",
    )
    opened_by_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Snapshot of the opening user's display name at the time — survives later name changes",
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Device-local timestamp the session was closed — NULL while still open",
    )
    closing_cash_cents: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Cash counted out of the till at close; NULL while still open",
    )
    expected_cash_cents: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="opening_cash_cents + cash takings recorded against this session; NULL while still open",
    )
    variance_cents: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="closing_cash_cents - expected_cash_cents; NULL while still open",
    )
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="POS user who closed the session; NULL while still open or if later deleted",
    )
    closed_by_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Snapshot of the closing user's display name at the time; NULL while still open",
    )
    client_ref: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
        comment=(
            "Client-generated idempotency key for the OPEN call (UUID minted on-device) — "
            "a retried POST /register-sessions/open with the same client_ref returns the "
            "original row instead of raising 409 for a device that already has one open."
        ),
    )
    close_client_ref: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
        comment=(
            "Client-generated idempotency key for the CLOSE call — a retried close with the "
            "same close_client_ref returns the already-closed row instead of raising 400."
        ),
    )
    checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment=(
            "SHA-256 hex digest over this session's canonical counts/totals, re-verified at "
            "open and again (overwritten) at close — see app.utils.checksum. Always the "
            "server's own computed digest, echoed back so the device can confirm what was stored."
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Server-side bookkeeping timestamp — distinct from the device-local opened_at",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
