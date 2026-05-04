"""SQLAlchemy ORM model for the pos_devices table.

A PosDevice represents a physical Android terminal that has been registered to
a Site under an active License. Each device has a unique token used to
authenticate POS login calls. Duplicate registration (same device_token) is
rejected with HTTP 409.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PosDevice(Base):
    """A registered Android POS terminal associated with a Site and License."""

    __tablename__ = "pos_devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="The site this device operates at",
    )
    license_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("licenses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="License that authorises this device to run",
    )
    device_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable display name for the device",
    )
    device_token: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        comment="Unique token used to authenticate POS login calls from this device",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when the device has been deregistered",
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="UTC timestamp of first registration",
    )

    license: Mapped["License"] = relationship(  # type: ignore[name-defined]
        "License",
        back_populates="devices",
    )
