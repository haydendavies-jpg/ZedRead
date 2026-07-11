"""SQLAlchemy ORM model for combo groups (sub-product selection groups)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductComboGroup(Base):
    """
    A selection group within a combo product.

    Example: "Burger Meal" has a combo group "Choose a side" (required, pick 1)
    and another "Choose a drink" (required, pick 1).

    Combo products reference other products as their options. The circular
    reference check in combo_service.py prevents A→B→A cycles.

    This is the "Combo" entity surfaced by the Stage 22 portal page — there is
    no separate Combo table; a combo product is simply a Product that owns one
    or more of these groups. ref/display_name/is_active were added by
    migration 0039 so Combos get the same ref-code and status-toggle table UX
    as Products and Variants.
    """

    __tablename__ = "product_combo_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    ref: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        server_default=text("'CMB-' || LPAD(nextval('product_combo_groups_ref_seq')::text, 6, '0')"),
        comment="Human-readable reference ID, e.g. CMB-000001",
    )
    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Management-facing label distinct from the POS-facing internal name",
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The combo product this group belongs to",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Display name shown on the POS, e.g. 'Choose a side'",
    )
    min_selections: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Minimum number of options the cashier must pick (1 = required)",
    )
    max_selections: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Maximum number of options the cashier may pick",
    )
    is_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="True when the cashier must select at least one option",
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Order in which this group is shown during order entry",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when the combo group is soft-deleted — matches product_variants.is_active",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
