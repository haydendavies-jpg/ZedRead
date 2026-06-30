"""Make User.brand_id optional and add User.group_id; make AccessProfile group-aware.

Part of Stage 15 (Identity & Permissions Redesign). Master Users are being
extended to exist at Group and Brand level, not just Site. A Group-level
Master User has no Brand to belong to, so User.brand_id must become
optional. Every User still belongs to exactly one Group, so User.group_id
becomes required (backfilled from the existing brand_id -> brands.group_id
relationship, which is exact since every existing User has a brand_id today).

AccessProfile gains the same group_id/brand_id mutually-exclusive-scope
pattern UserAccessGrant already uses, since a scope='group' grant still
needs a real access_profile_id to reference and the existing AccessProfile
table is strictly brand-scoped.

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add users.group_id (backfilled, then NOT NULL), relax users.brand_id,
    add access_profiles.group_id, relax access_profiles.brand_id, and add
    the scope-consistency check constraint on access_profiles."""
    # users.group_id — add nullable first so the backfill UPDATE can run
    op.add_column(
        "users",
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    # Backfill from the existing brand_id -> brands.group_id relationship.
    # Exact for every existing row: every User today has a brand_id.
    op.execute(
        "UPDATE users SET group_id = brands.group_id "
        "FROM brands WHERE brands.id = users.brand_id"
    )
    op.alter_column("users", "group_id", nullable=False)
    op.create_foreign_key(
        "fk_users_group_id_groups",
        "users",
        "groups",
        ["group_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_users_group_id", "users", ["group_id"])

    # users.brand_id becomes optional — NULL for a Group-level Master User
    op.alter_column("users", "brand_id", nullable=True)

    # access_profiles.group_id — mirrors UserAccessGrant's scope FK pattern
    op.add_column(
        "access_profiles",
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_access_profiles_group_id_groups",
        "access_profiles",
        "groups",
        ["group_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_access_profiles_group_id", "access_profiles", ["group_id"])

    # access_profiles.brand_id becomes optional — NULL for a group-scoped profile
    op.alter_column("access_profiles", "brand_id", nullable=True)

    op.create_check_constraint(
        "ck_access_profiles_scope_fk_consistency",
        "access_profiles",
        "(brand_id IS NOT NULL AND group_id IS NULL) OR "
        "(brand_id IS NULL AND group_id IS NOT NULL)",
    )


def downgrade() -> None:
    """Revert AccessProfile group-scoping and User.group_id/brand_id changes."""
    op.drop_constraint(
        "ck_access_profiles_scope_fk_consistency", "access_profiles", type_="check"
    )
    op.alter_column("access_profiles", "brand_id", nullable=False)
    op.drop_index("ix_access_profiles_group_id", table_name="access_profiles")
    op.drop_constraint(
        "fk_access_profiles_group_id_groups", "access_profiles", type_="foreignkey"
    )
    op.drop_column("access_profiles", "group_id")

    op.alter_column("users", "brand_id", nullable=False)
    op.drop_index("ix_users_group_id", table_name="users")
    op.drop_constraint("fk_users_group_id_groups", "users", type_="foreignkey")
    op.drop_column("users", "group_id")
