"""SQLAlchemy ORM model for user access grants (user ↔ site ↔ profile link)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserAccessGrant(Base):
    """
    Links a POSUser to a Site with a specific AccessProfile.

    A user may have grants for multiple sites with different profiles —
    e.g. Manager at one site, Cashier at another. Only active grants are
    checked at login time.
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
        comment="The permission profile applied at this site",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when the grant has been revoked",
    )
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portal_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Portal user who created this grant; null if created by system",
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
