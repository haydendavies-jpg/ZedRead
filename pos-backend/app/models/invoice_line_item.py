"""SQLAlchemy ORM model for invoice line items.

SNAPSHOT RULE (Stage 10): product_name, unit_price_cents, tax_rate_name,
tax_rate_percent, and tax_model are all COPIED at the time the line item is
added.  They are NEVER foreign keys — they must remain correct even after
the product is updated, renamed, or deleted.  Violation of this rule would
corrupt all historical invoice data.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InvoiceLineItem(Base):
    """
    One line of an invoice — a product at a specific price and quantity.

    All product and tax data is SNAPSHOTTED onto this row at creation time.
    The product_id FK is kept for optional reference/reporting but is SET NULL
    on delete so historical invoices survive product removal.
    """

    __tablename__ = "invoice_line_items"

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
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        comment="Reference to the source product; SET NULL if product is deleted (snapshot is the truth)",
    )
    # ── SNAPSHOT FIELDS — never update these after creation ──────────────────
    product_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="SNAPSHOT: product name at time of sale",
    )
    unit_price_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="SNAPSHOT: effective price per unit in cents at time of sale",
    )
    tax_category_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="SNAPSHOT: tax category name at time of sale (NULL if no tax)",
    )
    # Combined tax rate across all rates in the category (stored for reporting)
    tax_rate_percent: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        default=Decimal("0"),
        comment="SNAPSHOT: aggregate tax rate percent applied to this line",
    )
    tax_model: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="exclusive",
        comment="SNAPSHOT: tax model applied (inclusive/exclusive/compound)",
    )
    # ── Computed quantities ───────────────────────────────────────────────────
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Number of units sold",
    )
    subtotal_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="unit_price_cents × quantity (before tax for exclusive)",
    )
    tax_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Tax collected on this line item across all applicable rates",
    )
    line_total_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Amount charged to the customer for this line (subtotal + exclusive tax)",
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Print order on the receipt",
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional line-level notes (e.g. dietary notes)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
