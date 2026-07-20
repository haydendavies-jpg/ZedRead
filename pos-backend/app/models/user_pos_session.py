"""SQLAlchemy ORM model for active POS terminal sessions."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserPOSSession(Base):
    """
    Records an active or completed POS session for a user at a site.

    A session begins when a user logs in to a terminal and ends when they
    log out or the JWT expires. The token_jti (JWT ID claim) allows
    individual sessions to be revoked without invalidating all user tokens.

    ended_at is null while the session is active.
    """

    __tablename__ = "user_pos_sessions"

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
        index=True,
        comment="The POS user who started this session",
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The site (terminal) where the session is running",
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pos_devices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="The terminal this session was opened from — nullable for pre-existing rows",
    )
    # jti from the JWT payload — used for future token revocation support
    token_jti: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
        index=True,
        comment="JWT ID claim — unique per token, enables per-session revocation",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the session was created",
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Set on logout; null means the session is still active",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
