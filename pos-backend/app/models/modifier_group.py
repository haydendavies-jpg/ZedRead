"""SQLAlchemy ORM model for modifier groups (e.g. Add-ons, Sauce choice)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ModifierGroup(Base):
    """
    A named group of optional or required add-ons for products.

    Examples: "Extra Toppings" (optional, max 3), "Choose a sauce" (required, exactly 1).

    min_selections / max_selections control how many options the cashier must
    choose from this group when adding a product to an order. has_quantity
    lets the same option be selected more than once (per-option quantity),
    still capped by max_selections in total.
    """

    __tablename__ = "modifier_groups"

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
        comment="Brand this modifier group belongs to — not shared across brands",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Display name shown on the POS, e.g. 'Extra Toppings'",
    )
    min_selections: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Minimum number of options the cashier must choose (0 = optional)",
    )
    max_selections: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Maximum number of options the cashier may choose",
    )
    has_quantity: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True — the same option may be selected multiple times (per-option quantity), up to max_selections total",
    )
    is_first_option_default_selected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True — the POS pre-selects this group's first option when the customise sheet opens. "
        "False (the default) leaves every group unselected until the cashier actually picks something.",
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Order groups appear in on the POS and the Modifiers tab — lower values first. A "
        "product's own product_modifier_group_links.display_order (Stage 23's per-product "
        "reorder) overrides this for that product only.",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when soft-deleted; inactive groups are excluded from POS",
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
