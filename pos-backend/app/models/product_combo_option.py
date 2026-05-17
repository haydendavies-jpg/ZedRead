"""SQLAlchemy ORM model for individual options within a combo group."""

import uuid

from sqlalchemy import BigInteger, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductComboOption(Base):
    """
    A product that can be selected as an option within a ProductComboGroup.

    price_delta_cents is the additional charge (or discount) when this option
    is chosen — typically 0 for standard inclusions. The referenced product_id
    must not create a circular combo chain (enforced by combo_service.py).
    """

    __tablename__ = "product_combo_options"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    combo_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_combo_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The combo group this option belongs to",
    )
    # The product offered as an option — must not create a circular reference
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        comment="The product that can be chosen as this combo option",
    )
    # BIGINT cents — 0 for standard inclusions, positive for upgrades; rule 4 + 9
    price_delta_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Extra charge for selecting this option; 0 = included in combo price",
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Sort order within the combo group",
    )
