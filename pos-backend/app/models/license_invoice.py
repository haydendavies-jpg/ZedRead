"""SQLAlchemy ORM model for the license_invoices table.

Each row represents a billing event raised against a License. Invoices are
immutable once paid — marking one paid sets paid_at and cannot be undone.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LicenseInvoice(Base):
    """A billing event (monthly charge) linked to a License."""

    __tablename__ = "license_invoices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    license_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("licenses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Parent license — restricts deletion of a licensed site",
    )
    amount_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Invoice amount in the smallest currency unit (cents)",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        comment="Billing state — open | paid | cancelled",
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="First day of the billing period this invoice covers",
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Last day of the billing period this invoice covers",
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC timestamp when payment was received; null while unpaid",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    license: Mapped["License"] = relationship(  # type: ignore[name-defined]
        "License",
        back_populates="invoices",
    )
