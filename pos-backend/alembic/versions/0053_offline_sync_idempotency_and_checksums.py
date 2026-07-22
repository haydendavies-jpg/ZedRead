"""Android POS Phase 2 — idempotency (client_ref) and checksum columns.

client_ref is a client-generated UUID minted on-device at write time,
deduped via a unique constraint: a retried offline write (invoice creation,
a payment leg, register-session open/close) that already landed server-side
returns the original row instead of creating a duplicate. register_sessions
gets two separate client_ref columns (open vs. close) since a single
session row is written to twice, by two independent idempotent calls.

checksum is a SHA-256 hex digest over each entity's canonical
line-items/totals/payments (invoices) or counts/totals (register_sessions)
payload — always the server's own computed digest (see app.utils.checksum),
re-verified against whatever the device supplied so a mismatch is rejected
rather than silently accepted, and echoed back so the device can confirm
what was actually stored.

Revision ID: 0053
Revises: 0052
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add client_ref/checksum columns to invoices, payments, and register_sessions."""
    op.add_column(
        "invoices",
        sa.Column(
            "client_ref",
            sa.String(64),
            nullable=True,
            unique=True,
            comment="Client-generated idempotency key for POST /invoices — dedupes a retried offline create",
        ),
    )
    op.add_column(
        "invoices",
        sa.Column(
            "checksum",
            sa.String(64),
            nullable=True,
            comment="Server-computed SHA-256 over the invoice's canonical line items/totals/payments",
        ),
    )

    op.add_column(
        "payments",
        sa.Column(
            "client_ref",
            sa.String(64),
            nullable=True,
            unique=True,
            comment="Client-generated idempotency key for POST .../pay — dedupes a retried offline payment leg",
        ),
    )

    op.add_column(
        "register_sessions",
        sa.Column(
            "client_ref",
            sa.String(64),
            nullable=True,
            unique=True,
            comment="Client-generated idempotency key for the OPEN call",
        ),
    )
    op.add_column(
        "register_sessions",
        sa.Column(
            "close_client_ref",
            sa.String(64),
            nullable=True,
            unique=True,
            comment="Client-generated idempotency key for the CLOSE call",
        ),
    )
    op.add_column(
        "register_sessions",
        sa.Column(
            "checksum",
            sa.String(64),
            nullable=True,
            comment="Server-computed SHA-256 over the session's canonical counts/totals",
        ),
    )


def downgrade() -> None:
    """Drop the idempotency/checksum columns in reverse order."""
    op.drop_column("register_sessions", "checksum")
    op.drop_column("register_sessions", "close_client_ref")
    op.drop_column("register_sessions", "client_ref")
    op.drop_column("payments", "client_ref")
    op.drop_column("invoices", "checksum")
    op.drop_column("invoices", "client_ref")
