"""SQLAlchemy ORM model for payments against an invoice."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Payment(Base):
    """
    Records one payment event against an invoice.

    A split payment uses two Payment rows (e.g. partial cash + card).
    The invoice is considered PAID when the sum of payments >= total_cents.
    method must be a value from PaymentMethod enum (statuses.py).
    """

    __tablename__ = "payments"

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
        comment="Invoice being paid — cascades deletion",
    )
    method: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Payment method: cash, card, or voucher (from PaymentMethod enum)",
    )
    amount_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Amount tendered in this payment event",
    )
    reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Card terminal reference number or voucher code; NULL for cash",
    )
    paid_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Timestamp of this payment event",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
