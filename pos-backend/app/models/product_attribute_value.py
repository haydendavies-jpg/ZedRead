"""SQLAlchemy ORM model for product attribute values (e.g. Small, Medium, Large)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductAttributeValue(Base):
    """
    A concrete value for a ProductAttributeType.

    Examples: "Small", "Medium", "Large" under the "Size" type.

    Values are scoped to a single attribute type and have a display_order for
    the POS picker UI.
    """

    __tablename__ = "product_attribute_values"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    attribute_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_attribute_types.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent attribute type this value belongs to",
    )
    value: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="The concrete value label, e.g. 'Small', 'Red'",
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Sort order in the POS variant picker — lower values appear first",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
