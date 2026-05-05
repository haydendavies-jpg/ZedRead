"""SQLAlchemy ORM model for site-level product price and visibility overrides."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SiteProductOverride(Base):
    """
    Allows a site to override the price or visibility of a product.

    If override_price_cents is set, the site charges that price instead of
    the product's base_price_cents.  If is_excluded is True, the product does
    not appear in that site's catalog at all.

    The combination (site_id, product_id) is unique — only one override row
    per product per site.  Absence of a row means the site uses the brand defaults.
    """

    __tablename__ = "site_product_overrides"

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
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The product being overridden",
    )
    # NULL means no price override — use base_price_cents from products table
    override_price_cents: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Site-specific price in cents; NULL means use the product's base price",
    )
    is_excluded: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True hides the product from this site's catalog entirely",
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
