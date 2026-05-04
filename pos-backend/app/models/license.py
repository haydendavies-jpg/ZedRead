"""SQLAlchemy ORM model for the licenses table.

A License is the commercial entitlement that authorises a Site to run the POS
terminal. One license per site. Status transitions:
  active → expired  (nightly Celery task when expires_at < now())
  active → disabled (manual suspension)
  disabled → active (manual re-enable)
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class License(Base):
    """Commercial entitlement that allows a Site to operate its POS terminal."""

    __tablename__ = "licenses"

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
        unique=True,
        comment="One license per site — unique constraint enforced at DB level",
    )
    plan_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Subscription plan label (e.g. 'starter', 'pro', 'enterprise')",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="Lifecycle state — active | expired | disabled",
    )
    monthly_fee_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Recurring monthly fee in the smallest currency unit (cents)",
    )
    is_trial: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True for trial licenses that carry no invoicing obligation",
    )
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="UTC timestamp from which the license is valid",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="UTC timestamp after which the nightly task marks status=expired",
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

    invoices: Mapped[list["LicenseInvoice"]] = relationship(  # type: ignore[name-defined]
        "LicenseInvoice",
        back_populates="license",
        cascade="all, delete-orphan",
    )
    devices: Mapped[list["PosDevice"]] = relationship(  # type: ignore[name-defined]
        "PosDevice",
        back_populates="license",
        cascade="all, delete-orphan",
    )
