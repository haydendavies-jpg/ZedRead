"""SQLAlchemy ORM model for POS user invite tokens."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserInvite(Base):
    """
    A one-time invite token sent to a new POS user via email.

    The invite link contains the token. When accepted, the user sets their
    password and a UserAccessGrant is created for the specified site and
    access profile. The token is single-use and expires after a set period.
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
        comment="The brand the new user will belong to",
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        comment="The site the user will be granted access to on acceptance",
    )
    access_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("access_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        comment="The access profile to assign when the invite is accepted",
    )
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portal_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Portal user who sent the invite",
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Email address the invite was sent to",
    )
    # Cryptographically random token included in the invite link
    token: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique secret token included in the invite URL",
    )
    is_accepted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True once the invitee has set their password and created their account",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Token is invalid after this time",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
