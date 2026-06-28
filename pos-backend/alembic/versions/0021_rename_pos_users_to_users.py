"""Rename pos_users to users.

Part of Stage 15 (Identity & Permissions Redesign, see ROLE_MODEL.md): POSUser
is renamed to User — the customer-facing staff identity that always has POS
access and optionally has backend/portal access per grant. This migration is
a pure rename (table, sequence, indexes); the role-model changes (Group-level
storage, required-field rules, the 5-role model collapsing access_profiles)
are deferred to follow-up migrations.

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename pos_users table/sequence/indexes to users."""
    op.execute("ALTER SEQUENCE pos_users_ref_seq RENAME TO users_ref_seq")
    op.rename_table("pos_users", "users")
    op.execute("ALTER INDEX ix_pos_users_brand_id RENAME TO ix_users_brand_id")
    op.execute("ALTER INDEX ix_pos_users_email RENAME TO ix_users_email")
    op.execute("ALTER INDEX ix_pos_users_is_active RENAME TO ix_users_is_active")
    # The ref column's server_default references the sequence by name — point it
    # at the renamed sequence so newly inserted rows keep generating USR-xxxxxx refs.
    op.alter_column(
        "users",
        "ref",
        server_default=sa.text("'USR-' || LPAD(nextval('users_ref_seq')::text, 6, '0')"),
    )


def downgrade() -> None:
    """Revert users back to pos_users."""
    op.alter_column(
        "users",
        "ref",
        server_default=sa.text("'USR-' || LPAD(nextval('pos_users_ref_seq')::text, 6, '0')"),
    )
    op.execute("ALTER INDEX ix_users_is_active RENAME TO ix_pos_users_is_active")
    op.execute("ALTER INDEX ix_users_email RENAME TO ix_pos_users_email")
    op.execute("ALTER INDEX ix_users_brand_id RENAME TO ix_pos_users_brand_id")
    op.rename_table("users", "pos_users")
    op.execute("ALTER SEQUENCE users_ref_seq RENAME TO pos_users_ref_seq")
