"""SQLAlchemy ORM model for access profiles controlling POS user permissions."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AccessProfile(Base):
    """
    Defines a named permission tier for POS users within a brand.

    Four system profiles (Manager, Supervisor, Cashier, Kitchen) are seeded
    automatically when a brand is created. Additional custom profiles can be
    created by brand admins. System profiles cannot be deleted (is_system=True).
    """

    __tablename__ = "access_profiles"

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
        comment="Brand this profile belongs to — profiles are not shared across brands",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable profile name, e.g. 'Manager', 'Cashier'",
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True for the 4 auto-seeded system profiles — these cannot be deleted",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when the profile is soft-deleted",
    )
    can_access_portal: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True when holders of this profile may log into the management portal",
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
