"""Rename portal_users to superadmins and collapse role values.

Part of Stage 15 (Identity & Permissions Redesign, see ROLE_MODEL.md): PortalUser
is renamed to SuperAdmin. The role enum collapses from super_admin|admin|reseller
to admin|reseller_staff — "Admin" becomes the single top role within the
SuperAdmin user type (the super_admin/admin split retired), and "reseller"
becomes "reseller_staff" to match the new role name. Existing super_admin rows
are remapped to admin since there is no longer a distinct tier above it.

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename portal_users table/sequence/indexes to superadmins and remap role values."""
    op.execute("ALTER SEQUENCE portal_users_ref_seq RENAME TO superadmins_ref_seq")
    op.rename_table("portal_users", "superadmins")
    op.execute("ALTER INDEX ix_portal_users_email RENAME TO ix_superadmins_email")
    op.execute(
        "ALTER INDEX ix_portal_users_password_reset_token "
        "RENAME TO ix_superadmins_password_reset_token"
    )
    op.execute("ALTER INDEX ix_portal_users_is_active RENAME TO ix_superadmins_is_active")
    op.execute("ALTER INDEX ix_portal_users_role RENAME TO ix_superadmins_role")
    # The ref column's server_default references the sequence by name — point it
    # at the renamed sequence so newly inserted rows keep generating PTL-xxxxxx refs.
    op.alter_column(
        "superadmins",
        "ref",
        server_default=sa.text("'PTL-' || LPAD(nextval('superadmins_ref_seq')::text, 6, '0')"),
    )
    # Collapse super_admin into admin (no remaining distinct tier above it) and
    # rename reseller to reseller_staff to match the new role name.
    op.execute("UPDATE superadmins SET role = 'admin' WHERE role = 'super_admin'")
    op.execute("UPDATE superadmins SET role = 'reseller_staff' WHERE role = 'reseller'")


def downgrade() -> None:
    """Revert superadmins back to portal_users, restoring the old role values."""
    op.execute("UPDATE superadmins SET role = 'reseller' WHERE role = 'reseller_staff'")
    op.alter_column(
        "superadmins",
        "ref",
        server_default=sa.text("'PTL-' || LPAD(nextval('portal_users_ref_seq')::text, 6, '0')"),
    )
    op.execute("ALTER INDEX ix_superadmins_role RENAME TO ix_portal_users_role")
    op.execute("ALTER INDEX ix_superadmins_is_active RENAME TO ix_portal_users_is_active")
    op.execute(
        "ALTER INDEX ix_superadmins_password_reset_token "
        "RENAME TO ix_portal_users_password_reset_token"
    )
    op.execute("ALTER INDEX ix_superadmins_email RENAME TO ix_portal_users_email")
    op.rename_table("superadmins", "portal_users")
    op.execute("ALTER SEQUENCE superadmins_ref_seq RENAME TO portal_users_ref_seq")
