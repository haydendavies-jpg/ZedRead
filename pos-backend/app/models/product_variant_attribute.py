"""SQLAlchemy ORM model for variant–attribute value assignments.

The composite primary key (variant_id, attribute_type_id) enforces that a
variant can have at most one value per attribute type — e.g. a "Burger" variant
cannot be both "Small" and "Large" for the "Size" dimension.
"""

import uuid

from sqlalchemy import ForeignKey, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductVariantAttribute(Base):
    """
    Links a ProductVariant to one ProductAttributeValue for each dimension.

    Composite PK (variant_id, attribute_type_id) is the key invariant:
    one value per attribute type per variant. The service layer checks for
    duplicate combinations before inserting to return a clean 409 rather
    than a DB constraint error.
    """

    __tablename__ = "product_variant_attributes"
    __table_args__ = (
        PrimaryKeyConstraint(
            "variant_id",
            "attribute_type_id",
            name="pk_product_variant_attributes",
        ),
    )

    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False,
        comment="The variant this attribute assignment belongs to",
    )
    attribute_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_attribute_types.id", ondelete="RESTRICT"),
        nullable=False,
        comment="The attribute dimension (e.g. 'Size')",
    )
    attribute_value_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_attribute_values.id", ondelete="RESTRICT"),
        nullable=False,
        comment="The concrete value chosen for this dimension (e.g. 'Large')",
    )
