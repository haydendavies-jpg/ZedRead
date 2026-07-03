"""A single named tax rate belonging to an admin-managed TaxTemplate."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TaxTemplateRate(Base):
    """One rate line under a TaxTemplate, e.g. 'GST' 10% inclusive.

    rate_percent is stored as NUMERIC(10, 4) — never a float (rule 9).
    Use Python's Decimal for all arithmetic involving this field.
    """

    __tablename__ = "tax_template_rates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    tax_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tax_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent template — rates are deleted with their template",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Rate label shown on receipts and tax breakdowns, e.g. 'GST'",
    )
    rate_percent: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        comment="Percentage as a decimal, e.g. 10.0000 for 10% — never a float",
    )
    tax_model: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="How the rate applies at invoice time: inclusive, exclusive, or compound",
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Ordering of rates within the template for display and receipts",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when soft-deleted; inactive rates are never applied",
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
