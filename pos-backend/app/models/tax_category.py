"""SQLAlchemy ORM model for tax categories (named tax groupings for a brand)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TaxCategory(Base):
    """
    A named tax grouping scoped to a brand, e.g. "Food", "Alcohol", "GST-Free".

    One or more TaxRates belong to each TaxCategory. Products and categories
    reference a TaxCategory; the active TaxRates under it determine what tax
    lines appear on an invoice.

    Examples:
      TaxCategory "Standard" → TaxRate "GST" 10% inclusive
      TaxCategory "Alcohol"  → TaxRate "GST" 10% + TaxRate "Alcohol Levy" 5%
    """

    __tablename__ = "tax_categories"

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
        comment="Parent brand — tax categories are not shared across brands",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable name shown in the portal and on receipts",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when soft-deleted; inactive categories cannot be assigned",
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
