"""SQLAlchemy ORM model for invoices — the primary transaction record."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Invoice(Base):
    """
    A sales or refund invoice for a site.

    IMPORTANT: monetary totals on this row are derived summaries only —
    the canonical source of truth for line prices and taxes is in
    invoice_line_items and invoice_tax_breakdowns.  Totals are recomputed
    each time a line item is added/removed.

    refund_of_id: self-referential FK to the original invoice being refunded.
    A refund invoice has invoice_type='refund' and status='paid' on creation.

    Snapshot rule (Stage 10 plan): InvoiceLineItem stores product_name,
    unit_price_cents, tax_rate_percent, tax_model as copied values.  This
    invoice row is NOT a snapshot — it references live brand_id and site_id
    FKs that must remain after the invoice is paid or voided.
    """

    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Brand scope — never null even after brand update",
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Site where the invoice was raised",
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="POS user who created the invoice; SET NULL if user is later deleted",
    )
    invoice_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="sale",
        comment="'sale' for a normal transaction, 'refund' for a refund invoice",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        comment="draft → open → paid | voided; refund invoices start at paid",
    )
    subtotal_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Sum of line item subtotals (unit_price × quantity), before tax for exclusive",
    )
    tax_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Total tax collected across all line items",
    )
    discount_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Total discount applied — subtracted from the total",
    )
    discount_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Free-text reason for the discount, printed on receipt",
    )
    total_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Final amount owed: subtotal + exclusive_tax - discount (inclusive tax already in subtotal)",
    )
    register_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("register_sessions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment=(
            "The till session this sale was rung up under. Nullable only for rows "
            "predating register sessions — creation is rejected without one, see "
            "register_session_service.get_open_session_or_404()."
        ),
    )
    table_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("table_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=(
            "The table occupancy this order is attached to (Android POS Phase 4's "
            "'Open order →' handoff from the Tables screen into Register) — NULL for "
            "counter-service sales with no table context."
        ),
    )
    refund_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
        comment="Self-referential FK to the invoice this record is refunding; NULL for sale invoices",
    )
    is_refunded: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True once a refund invoice has been created for this sale",
    )
    client_ref: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
        comment=(
            "Client-generated idempotency key (UUID minted on-device at creation time) — "
            "a retried POST /invoices with the same client_ref returns the original row "
            "instead of creating a duplicate. NULL for pre-offline-queue callers."
        ),
    )
    checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment=(
            "SHA-256 hex digest over the invoice's canonical line items/totals/payments, "
            "computed on-device and re-verified server-side at pay time (see "
            "app.utils.checksum) — the value stored here is always the server's own "
            "computed digest, echoed back so the device can confirm what was stored."
        ),
    )
    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when status was set to voided; NULL for non-voided invoices",
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of the final payment; NULL until invoice is fully paid",
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
