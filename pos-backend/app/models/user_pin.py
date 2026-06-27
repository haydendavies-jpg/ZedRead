"""SQLAlchemy ORM model for POS user PIN credentials."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserPIN(Base):
    """
    Stores the hashed PIN for a POS user.

    PINs are used for quick re-authentication at the terminal (e.g. switch
    user without full logout). One record per user — enforced by the unique
    constraint on user_id.

    The PIN hash uses argon2 (same as passwords). Raw PINs are never stored
    (CLAUDE.md rule 15).

    Note: the design document uses the field name `must_change` but CLAUDE.md
    rule 5 requires boolean columns to start with `is_` or `has_`. This model
    uses `is_pin_reset_required` instead.
    """

    __tablename__ = "user_pins"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # Enforce one PIN per user at the DB level
        comment="POS user this PIN belongs to — one-to-one relationship",
    )
    # Argon2 hash — never store the raw PIN (rule 15)
    pin_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Argon2 hash of the 4–6 digit PIN",
    )
    is_pin_reset_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True when the user must set a new PIN on next terminal login",
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
