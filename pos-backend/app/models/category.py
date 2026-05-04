"""SQLAlchemy ORM model for product categories (stub — extended in Stage 8).

This is the minimal schema required for Stage 3. Stage 8 adds columns
(display_order, description, image_url, tax_category_id) via a new migration
without removing or renaming any column defined here.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Category(Base):
    """
    A product category belonging to a Brand.

    The "Uncategorised" category (is_system=True) is auto-created when a brand
    is created and cannot be deleted. All products must belong to a category.
    """

    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # System categories (e.g. "Uncategorised") cannot be deleted or renamed
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    brand: Mapped["Brand"] = relationship("Brand", back_populates="categories")  # type: ignore[name-defined]
