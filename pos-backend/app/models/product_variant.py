"""SQLAlchemy ORM model for product variants."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductVariant(Base):
    """
    A specific combination of attribute values for a product, with its own price.

    Each variant represents one purchasable SKU — e.g. "Burger / Large / Spicy".
    If price_cents is NULL, the variant uses the parent product's base_price_cents.

    The exact attribute value combination must be unique per product (enforced
    by the composite PK on product_variant_attributes: variant_id + attribute_type_id).
    """

    __tablename__ = "product_variants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent product this variant belongs to",
    )
    sku: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Optional stock-keeping unit code for inventory integration",
    )
    # NULL means inherit from product.base_price_cents — rule 4 + 9
    price_cents: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Variant-specific price in cents; NULL means use the product's base price",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when the variant is soft-deleted",
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
