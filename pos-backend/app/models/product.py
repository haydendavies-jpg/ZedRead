"""SQLAlchemy ORM model for products in the catalog."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Product(Base):
    """
    A product in a brand's catalog.

    Prices are stored in cents (BIGINT) — never as floats (CLAUDE.md rule 4 + 9).
    base_price_cents is the default shelf price before any site-level override.

    A product belongs to a brand (scoping) and a category (display grouping).
    The tax_category_id is optional; if NULL the product inherits from its
    category's tax_category_id. The invoice engine resolves this chain.

    photo_url points to Supabase Storage — upload is handled by the product
    service, not directly stored here as binary data.
    """

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Parent brand — products are not shared across brands",
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Display category — must belong to the same brand",
    )
    tax_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tax_categories.id", ondelete="SET NULL"),
        nullable=True,
        comment="Product-level tax override; falls back to category's tax_category_id if NULL",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Display name shown on the POS and receipts",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional description shown in the portal and product detail screens",
    )
    # BIGINT cents — rule 4: every monetary column ends in _cents (rule 9: never float)
    base_price_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Default shelf price in cents — overridable per site via site_product_overrides",
    )
    photo_url: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="Supabase Storage URL for the product photo (max 500 KB enforced in service)",
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Sort order within the category — lower values appear first",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when soft-deleted; inactive products are excluded from the catalog",
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
