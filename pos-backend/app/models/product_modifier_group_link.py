"""SQLAlchemy ORM model for the many-to-many link between products and modifier groups."""

import uuid

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductModifierGroupLink(Base):
    """
    Associates a ModifierGroup with a Product.

    A product may have multiple modifier groups (e.g. "Sauce" and "Extras").
    display_order controls the sequence in which groups are presented to the
    cashier during order entry.
    """

    __tablename__ = "product_modifier_group_links"

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
        comment="The product this modifier group is attached to",
    )
    modifier_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modifier_groups.id", ondelete="CASCADE"),
        nullable=False,
        comment="The modifier group being linked",
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Order in which this group is presented during order entry",
    )
