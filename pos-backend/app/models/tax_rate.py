"""SQLAlchemy ORM model for individual tax rates within a tax category."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.statuses import TaxModel
from app.database import Base


class TaxRate(Base):
    """
    A single named tax rate belonging to a TaxCategory.

    rate_percent is stored as NUMERIC(10, 4) — never a float (rule 9).
    Use Python's Decimal for all arithmetic involving this field.

    tax_model controls how the rate is applied at invoice time:
      - inclusive: tax is embedded in the shelf price
      - exclusive: tax is added on top of the shelf price
      - compound: GST on base, then second rate on base (not on GST-inclusive total)

    A TaxCategory may have multiple active TaxRates (e.g. GST + a levy).
    """

    __tablename__ = "tax_rates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    tax_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tax_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent tax category this rate belongs to",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Label printed on receipts, e.g. 'GST', 'PST', 'Alcohol Levy'",
    )
    # NUMERIC(10, 4) — rule 9: never float for rates used in money calculations
    rate_percent: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        comment="Tax rate as a percentage, e.g. 10.0000 = 10%",
    )
    tax_model: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="How the rate is applied: inclusive, exclusive, or compound",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when soft-deleted; inactive rates are excluded from calculations",
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
