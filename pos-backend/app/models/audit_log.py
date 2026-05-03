"""SQLAlchemy ORM model for the audit_logs table — immutable event trail."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    """
    Immutable record of every state-changing action in the system.

    Rows are written in the same transaction as the business data change so
    they are guaranteed to be consistent — either both commit or both roll back.

    actor_email and actor_name are snapshotted at write time so the audit
    trail remains accurate even if the actor's details change later.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── Actor fields ──────────────────────────────────────────────────────────
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,  # Null when actor_type = 'system' (e.g. nightly Celery tasks)
        index=True,
    )
    actor_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'user' for human actors, 'system' for automated jobs",
    )
    actor_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Snapshotted email — preserved even if the actor changes their email later",
    )
    actor_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Snapshotted display name at time of action",
    )

    # ── Action fields ─────────────────────────────────────────────────────────
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Dot-separated action constant, e.g. 'invoice.paid'",
    )
    entity_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="The resource type affected, e.g. 'invoice', 'product'",
    )
    entity_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="String representation of the affected entity's primary key",
    )

    # ── State snapshot fields ─────────────────────────────────────────────────
    before_state: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Serialised entity state before the action (null for create actions)",
    )
    after_state: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Serialised entity state after the action (null for delete actions)",
    )

    # ── Request correlation ───────────────────────────────────────────────────
    request_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="UUID from X-Request-ID header — links audit row to the HTTP request",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Composite index: look up all actions on a specific entity efficiently
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
    )
