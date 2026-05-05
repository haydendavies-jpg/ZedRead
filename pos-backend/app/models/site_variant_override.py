"""SQLAlchemy ORM model for site-level variant price and visibility overrides."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SiteVariantOverride(Base):
    """
    Allows a site to override the price or visibility of a specific product variant.

    Mirrors the site_product_overrides pattern but at the variant level.
    If override_price_cents is set, the site charges that instead of the
    variant's price_cents (or the product base price if variant price is NULL).
    If is_excluded, the variant is hidden from the POS picker for this site.

    Unique per (site_id, variant_id).
    """

    __tablename__ = "site_variant_overrides"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The site this override applies to",
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The variant being overridden",
    )
    override_price_cents: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Site-specific variant price in cents; NULL means use the variant's price",
    )
    is_excluded: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True hides the variant from this site's picker",
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
