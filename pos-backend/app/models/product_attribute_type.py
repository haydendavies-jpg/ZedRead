"""SQLAlchemy ORM model for product attribute types (e.g. Size, Colour)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductAttributeType(Base):
    """
    A named dimension of variation for products within a brand.

    Examples: "Size", "Colour", "Temperature".

    Attribute types belong to a brand and are reused across multiple products.
    Each variant of a product stores exactly one value per attribute type
    (enforced by the composite primary key on product_variant_attributes).
    """

    __tablename__ = "product_attribute_types"

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
        comment="Brand this attribute type belongs to",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable dimension name, e.g. 'Size', 'Colour'",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
