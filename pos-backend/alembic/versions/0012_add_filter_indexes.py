"""Add indexes to support list-filter query params on groups, brands, sites,
portal_users, pos_users, licenses, products, and invoices.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-17
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create filter-support indexes on frequently queried columns."""

    # ── groups ──────────────────────────────────────────────────────────────
    op.create_index(
        "ix_groups_is_active", "groups", ["is_active"], if_not_exists=True
    )
    op.create_index(
        "ix_groups_name", "groups", ["name"], if_not_exists=True
    )

    # ── brands ──────────────────────────────────────────────────────────────
    op.create_index(
        "ix_brands_is_active", "brands", ["is_active"], if_not_exists=True
    )
    op.create_index(
        "ix_brands_name", "brands", ["name"], if_not_exists=True
    )

    # ── sites ────────────────────────────────────────────────────────────────
    op.create_index(
        "ix_sites_is_active", "sites", ["is_active"], if_not_exists=True
    )
    op.create_index(
        "ix_sites_name", "sites", ["name"], if_not_exists=True
    )

    # ── portal_users ─────────────────────────────────────────────────────────
    op.create_index(
        "ix_portal_users_is_active", "portal_users", ["is_active"], if_not_exists=True
    )
    op.create_index(
        "ix_portal_users_role", "portal_users", ["role"], if_not_exists=True
    )

    # ── pos_users ────────────────────────────────────────────────────────────
    op.create_index(
        "ix_pos_users_is_active", "pos_users", ["is_active"], if_not_exists=True
    )

    # ── licenses ─────────────────────────────────────────────────────────────
    op.create_index(
        "ix_licenses_status", "licenses", ["status"], if_not_exists=True
    )

    # ── products ─────────────────────────────────────────────────────────────
    op.create_index(
        "ix_products_is_active", "products", ["is_active"], if_not_exists=True
    )

    # ── invoices ─────────────────────────────────────────────────────────────
    op.create_index(
        "ix_invoices_created_at", "invoices", ["created_at"], if_not_exists=True
    )


def downgrade() -> None:
    """Drop all indexes added in this migration."""

    # ── invoices ─────────────────────────────────────────────────────────────
    op.drop_index("ix_invoices_created_at", table_name="invoices")

    # ── products ─────────────────────────────────────────────────────────────
    op.drop_index("ix_products_is_active", table_name="products")

    # ── licenses ─────────────────────────────────────────────────────────────
    op.drop_index("ix_licenses_status", table_name="licenses")

    # ── pos_users ────────────────────────────────────────────────────────────
    op.drop_index("ix_pos_users_is_active", table_name="pos_users")

    # ── portal_users ─────────────────────────────────────────────────────────
    op.drop_index("ix_portal_users_role", table_name="portal_users")
    op.drop_index("ix_portal_users_is_active", table_name="portal_users")

    # ── sites ────────────────────────────────────────────────────────────────
    op.drop_index("ix_sites_name", table_name="sites")
    op.drop_index("ix_sites_is_active", table_name="sites")

    # ── brands ──────────────────────────────────────────────────────────────
    op.drop_index("ix_brands_name", table_name="brands")
    op.drop_index("ix_brands_is_active", table_name="brands")

    # ── groups ──────────────────────────────────────────────────────────────
    op.drop_index("ix_groups_name", table_name="groups")
    op.drop_index("ix_groups_is_active", table_name="groups")
