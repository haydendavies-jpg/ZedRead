"""SQLAlchemy ORM model for POS user access grants linking users to sites."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserAccessGrant(Base):
    """
    Links a POS user to a site with a specific access profile.

    A grant says: "this user may use this site with these permissions."
    Multiple grants per user are allowed (one per site). Grants are soft-deleted
    via is_active rather than hard-deleted so the audit trail is preserved.

    granted_by_id is nullable so that system-created grants (e.g. during
    invite acceptance) can set it to None before the actor is known.
    """

    __tablename__ = "user_access_grants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pos_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The POS user being granted access",
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The site the user is being granted access to",
    )
    access_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("access_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        comment="The access profile (permission tier) for this grant",
    )
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pos_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="The POS user who created this grant, or NULL for system grants",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when the grant has been revoked",
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
