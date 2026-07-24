"""SQLAlchemy ORM model for print templates (Invoice / Order Docket / Register Summary / Cash-in Slip)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PrintTemplate(Base):
    """
    A customisable print layout — an ordered set of PrintTemplateElement rows.

    template_type is one of 'invoice' | 'docket' | 'register_summary' |
    'cash_in_slip'. 'invoice'/'register_summary'/'cash_in_slip' are brand-wide
    singletons (enforced by a partial unique index on (brand_id, template_type)
    where template_type != 'docket' — see the migration); 'docket' templates
    are one-per-PrinterLocation instead, via printer_location_id's own unique
    constraint, auto-created alongside their location
    (printer_location_service.create_printer_location()).
    """

    __tablename__ = "print_templates"

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
        comment="Parent brand — templates are not shared across brands",
    )
    printer_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("printer_locations.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
        comment="Set only when template_type='docket' — one docket template per location",
    )
    template_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'invoice' | 'docket' | 'register_summary' | 'cash_in_slip'",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Display name shown in the portal's Printer Templates list",
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

    elements: Mapped[list["PrintTemplateElement"]] = relationship(  # type: ignore[name-defined]
        "PrintTemplateElement", cascade="all, delete-orphan", passive_deletes=True
    )
