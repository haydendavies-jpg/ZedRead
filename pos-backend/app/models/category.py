"""SQLAlchemy ORM model for product categories.

The Stage 3 stub had: id, brand_id, name, is_system, is_active, created_at.
Stage 8 adds: display_order, description, image_url, tax_category_id.
No Stage 3 columns were removed or renamed — the extension is additive only.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Category(Base):
    """
    A product category belonging to a Brand.

    The "Uncategorised" category (is_system=True) is auto-created when a brand
    is created and cannot be deleted. All products must belong to a category.

    A category may have a default tax_category_id; products within it inherit
    this tax category unless they override it individually.
    """

    __tablename__ = "categories"

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
        comment="Parent brand — categories are not shared across brands",
    )
    # Nullable FK — set after tax_categories table exists (migration 0006)
    tax_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tax_categories.id", ondelete="SET NULL"),
        nullable=True,
        comment="Default tax category for products in this category (optional)",
    )
    reporting_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reporting_groups.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Required reporting group this category rolls up to (Stage 16)",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Display name shown in the POS category tab strip",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional long-form description for the portal UI",
    )
    image_url: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="URL of the category header image (stored in Supabase Storage)",
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Sort order for the category tab strip — lower values appear first",
    )
    # System categories (e.g. "Uncategorised") cannot be deleted or renamed
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True for auto-seeded categories that cannot be deleted",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when the category is soft-deleted",
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

    brand: Mapped["Brand"] = relationship("Brand", back_populates="categories")  # type: ignore[name-defined]
    reporting_group: Mapped["ReportingGroup"] = relationship(  # type: ignore[name-defined]
        "ReportingGroup", back_populates="categories"
    )
