"""SQLAlchemy ORM model for per-rate tax breakdown on an invoice.

One row per tax rate applied — used to print an itemised tax summary on receipts
and to populate the reporting views in Stage 11.

All rate data is snapshotted at invoice creation time.
"""

import uuid
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InvoiceTaxBreakdown(Base):
    """
    Tax collected for one rate across all applicable line items on an invoice.

    tax_category_id and tax_rate_id are SET NULL soft references — the
    snapshot name, rate_percent, and tax_model fields are the canonical record.
    """

    __tablename__ = "invoice_tax_breakdowns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent invoice — cascades deletion",
    )
    tax_rate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tax_rates.id", ondelete="SET NULL"),
        nullable=True,
        comment="Reference to the source tax rate; SET NULL if rate is deleted",
    )
    # ── SNAPSHOT FIELDS ───────────────────────────────────────────────────────
    tax_rate_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="SNAPSHOT: tax rate name (e.g. 'GST', 'PST') at time of sale",
    )
    rate_percent: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        comment="SNAPSHOT: rate as a percentage at time of sale",
    )
    tax_model: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="SNAPSHOT: tax model (inclusive/exclusive/compound) at time of sale",
    )
    # ── Computed totals ───────────────────────────────────────────────────────
    taxable_amount_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Total base amount that this rate was applied to across all line items",
    )
    tax_amount_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Total tax collected for this rate across all line items",
    )
