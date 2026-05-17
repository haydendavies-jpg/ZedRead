"""SQLAlchemy ORM model for modifiers attached to an invoice line item.

All modifier data is snapshotted — modifier_name and price_delta_cents
are copied at invoice creation time, not linked live to modifier_options.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InvoiceLineModifier(Base):
    """
    A single modifier selection attached to an invoice line item.

    modifier_option_id is kept as a soft reference (SET NULL on delete)
    but modifier_name and price_delta_cents are SNAPSHOT values.
    """

    __tablename__ = "invoice_line_modifiers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    line_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoice_line_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent line item — cascades deletion",
    )
    modifier_option_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modifier_options.id", ondelete="SET NULL"),
        nullable=True,
        comment="Reference to the source modifier option; SET NULL if option is deleted",
    )
    # ── SNAPSHOT FIELDS ───────────────────────────────────────────────────────
    modifier_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="SNAPSHOT: modifier option name at time of sale",
    )
    price_delta_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="SNAPSHOT: price adjustment in cents at time of sale (can be negative)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
