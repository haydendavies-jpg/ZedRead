"""SQLAlchemy ORM model for individual options within a modifier group."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ModifierOption(Base):
    """
    A single selectable item within a ModifierGroup.

    Examples: "Extra Cheese +$1.50", "No Onion +$0.00".

    price_delta_cents is added to the line item total when selected.
    It may be zero (free modifier) or negative (discount modifier).
    """

    __tablename__ = "modifier_options"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    modifier_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modifier_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent modifier group this option belongs to",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Label shown on the POS, e.g. 'Extra Cheese'",
    )
    # BIGINT cents — may be 0 (free) or negative (discount); rule 4 + 9
    price_delta_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Amount added to the line item in cents; 0 = free modifier",
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Sort order within the group — lower values appear first",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when soft-deleted",
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
