"""SQLAlchemy ORM model for printer locations (kitchen/bar/etc. print stations)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PrinterLocation(Base):
    """
    A named print station (e.g. "Kitchen", "Bar") that products are assigned to.

    Order dockets are grouped and printed per location — every product sharing
    a location on one order prints together, using that location's own docket
    PrintTemplate (auto-created alongside this row — see
    printer_location_service.create_printer_location()). Printer-to-location
    pairing itself is local to each Android terminal, not stored here.
    """

    __tablename__ = "printer_locations"
    __table_args__ = (
        CheckConstraint("copy_count >= 1", name="ck_printer_locations_copy_count_min"),
    )

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
        comment="Parent brand — printer locations are not shared across brands",
    )
    ref: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        server_default=text("'PRN-' || LPAD(nextval('printer_locations_ref_seq')::text, 6, '0')"),
        comment="Human-readable reference ID, e.g. PRN-000001",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Display name, e.g. 'Kitchen', 'Bar'",
    )
    copy_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="Number of times the order docket is printed for this location — always >= 1",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when the location is soft-deleted",
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
