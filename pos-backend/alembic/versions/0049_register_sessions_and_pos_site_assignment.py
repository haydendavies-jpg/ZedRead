"""Android POS Phase 1 — register_sessions, users.is_pos_multi_site_enabled,
invoices.register_session_id.

register_sessions is a per-device (not per-site) cash-accountability shift:
opened when staff enter start-of-day cash, closed at cash-up. A partial
unique index enforces at most one open session per device. Invoices gain a
nullable register_session_id FK — nullable only so existing rows remain
valid; new invoice creation is rejected without an open session at the
service layer (see register_session_service.py), not by a NOT NULL
constraint, since that would break the existing invoices table in place.

users.is_pos_multi_site_enabled ("POS - Site Assignment") gates whether POS
login shows a site selector for a user with grants on more than one site.

user_pos_sessions.device_id (nullable — old rows/tokens carry no device
context) lets every POS-authenticated request resolve which terminal it
came from, which register_session_service needs to gate invoice creation
on a per-device open till session.

Revision ID: 0049
Revises: 0048
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create register_sessions and add the two new FK/flag columns."""
    op.create_table(
        "register_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pos_devices.id", ondelete="RESTRICT"),
            nullable=False,
            comment="The terminal this session belongs to — sessions are per-device, not per-site",
        ),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Denormalized from the device for simpler site-scoped portal reporting queries",
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Device-local timestamp the session was opened — supplied by the client",
        ),
        sa.Column("opening_cash_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "opened_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("opened_by_name", sa.String(255), nullable=False),
        sa.Column(
            "closed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Device-local timestamp the session was closed",
        ),
        sa.Column("closing_cash_cents", sa.BigInteger(), nullable=True),
        sa.Column("expected_cash_cents", sa.BigInteger(), nullable=True),
        sa.Column("variance_cents", sa.BigInteger(), nullable=True),
        sa.Column(
            "closed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("closed_by_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_register_sessions_device_id", "register_sessions", ["device_id"])
    op.create_index("ix_register_sessions_site_id", "register_sessions", ["site_id"])
    op.create_index(
        "uq_register_sessions_one_open_per_device",
        "register_sessions",
        ["device_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )

    op.add_column(
        "invoices",
        sa.Column(
            "register_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("register_sessions.id", ondelete="RESTRICT"),
            nullable=True,
            comment="The till session this sale was rung up under — nullable only for pre-existing rows",
        ),
    )
    op.create_index("ix_invoices_register_session_id", "invoices", ["register_session_id"])

    op.add_column(
        "users",
        sa.Column(
            "is_pos_multi_site_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="'POS - Site Assignment' — gates the POS login site selector",
        ),
    )

    op.add_column(
        "user_pos_sessions",
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pos_devices.id", ondelete="SET NULL"),
            nullable=True,
            comment="The terminal this session was opened from — nullable for pre-existing rows",
        ),
    )
    op.create_index("ix_user_pos_sessions_device_id", "user_pos_sessions", ["device_id"])


def downgrade() -> None:
    """Drop the new column/table additions in reverse order."""
    op.drop_index("ix_user_pos_sessions_device_id", table_name="user_pos_sessions")
    op.drop_column("user_pos_sessions", "device_id")
    op.drop_column("users", "is_pos_multi_site_enabled")
    op.drop_index("ix_invoices_register_session_id", table_name="invoices")
    op.drop_column("invoices", "register_session_id")
    op.drop_index("uq_register_sessions_one_open_per_device", table_name="register_sessions")
    op.drop_index("ix_register_sessions_site_id", table_name="register_sessions")
    op.drop_index("ix_register_sessions_device_id", table_name="register_sessions")
    op.drop_table("register_sessions")
