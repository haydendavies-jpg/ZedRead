"""SQLAlchemy ORM model for access profiles (permission templates seeded per brand)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AccessProfile(Base):
    """
    An AccessProfile is a named permission template that controls what a POS
    user can do at the terminal (e.g. apply discounts, void invoices).

    Four system profiles are automatically seeded when a Brand is created:
    Manager, Supervisor, Cashier, Kitchen. These cannot be deleted
    (is_system=True). Custom profiles may be added in a future stage.

    A user is linked to a profile per Site via UserAccessGrant.
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
        comment="Each brand owns its own set of access profiles",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Display name — e.g. 'Manager', 'Cashier'",
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True for the 4 auto-seeded profiles; prevents deletion",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Inactive profiles cannot be assigned to new grants",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
