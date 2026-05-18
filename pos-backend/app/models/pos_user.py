"""SQLAlchemy ORM model for POS users (staff who use the Android terminal)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class POSUser(Base):
    """
    A POS user is a member of staff who logs into the Android terminal.

    POS users belong to a Brand (not a Group) and are granted access to
    specific Sites via UserAccessGrant. They authenticate via email+password
    for initial login and via PIN for quick session switching at the terminal.
    """

    __tablename__ = "pos_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Parent brand — POS users are scoped to a brand, not a group",
    )
    ref: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        server_default=text("'USR-' || LPAD(nextval('pos_users_ref_seq')::text, 6, '0')"),
        comment="Human-readable reference ID, e.g. USR-000001",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Full display name shown on the terminal",
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Login email — must be unique across all POS users",
    )
    # Argon2 password hash — never store plaintext (rule 15)
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Argon2 hash of the user's password",
    )
    # Portal/backend access level — separate from POS terminal access profile
    # Values: 'admin' | 'users' | 'reporting'; NULL = no backend/portal access
    backend_role: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Backend/portal access level. NULL means no backend access.",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when the user is suspended and cannot log in",
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
