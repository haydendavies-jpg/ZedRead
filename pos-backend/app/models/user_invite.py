"""SQLAlchemy ORM model for POS user invitations sent via email."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserInvite(Base):
    """
    A pending email invitation for a new POS user.

    When a brand admin sends an invite, a row is created here with a unique
    token. The invitee clicks the link, accepts the invite, and a User +
    UserAccessGrant row are created in the same transaction. The invite is
    then marked is_accepted=True.

    Invites expire at expires_at — the acceptance route checks this before
    processing.
    """

    __tablename__ = "user_invites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Brand the invitee will be a member of",
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        comment="Site the invitee will be granted access to",
    )
    access_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("access_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Access profile the invitee will receive on acceptance",
    )
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="POS user who sent the invite, or NULL if sent by a portal admin",
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Email address the invitation was sent to",
    )
    # Secure random token embedded in the invite link — never derived from user data
    token: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique random token embedded in the invite URL",
    )
    is_accepted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True once the invitee has accepted and created their account",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="UTC timestamp after which the invite link is no longer valid",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
