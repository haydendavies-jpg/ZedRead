"""Stage 13 — management access: extend access_profiles and user_access_grants
for hierarchical portal login.

Adds can_access_portal to access_profiles and scope/brand_id/group_id to
user_access_grants, making site_id nullable. Existing site-scope grants are
safe: the migration default scope='site' satisfies the new check constraint
and all existing rows retain their non-null site_id value.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Extend access_profiles and user_access_grants for management portal access."""

    # ── access_profiles: add can_access_portal ──────────────────────────────
    op.add_column(
        "access_profiles",
        sa.Column(
            "can_access_portal",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="True when holders of this profile may log into the management portal",
        ),
    )
    # Retroactively enable portal access for all existing Manager system profiles
    op.execute(
        "UPDATE access_profiles SET can_access_portal = TRUE "
        "WHERE name = 'Manager' AND is_system = TRUE"
    )

    # ── user_access_grants: add scope + brand_id + group_id ─────────────────
    # 1. Relax site_id to nullable (existing rows all have a value — safe)
    op.alter_column("user_access_grants", "site_id", nullable=True)

    # 2. Add scope column — default 'site' keeps existing rows valid
    op.add_column(
        "user_access_grants",
        sa.Column(
            "scope",
            sa.String(10),
            nullable=False,
            server_default="site",
            comment="Scope of this grant: 'site', 'brand', or 'group'",
        ),
    )

    # 3. Add brand_id FK
    op.add_column(
        "user_access_grants",
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=True,
            comment="Set when scope='brand' — the brand this grant covers",
        ),
    )

    # 4. Add group_id FK
    op.add_column(
        "user_access_grants",
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=True,
            comment="Set when scope='group' — the group this grant covers",
        ),
    )

    # 5. Indexes for hierarchical grant lookups
    op.create_index(
        "ix_user_access_grants_brand_id", "user_access_grants", ["brand_id"]
    )
    op.create_index(
        "ix_user_access_grants_group_id", "user_access_grants", ["group_id"]
    )

    # 6. Check constraint: exactly one FK matches the scope value
    op.create_check_constraint(
        "ck_user_access_grants_scope_fk_consistency",
        "user_access_grants",
        "(scope = 'site'  AND site_id  IS NOT NULL AND brand_id IS NULL    AND group_id IS NULL) OR "
        "(scope = 'brand' AND brand_id IS NOT NULL AND site_id  IS NULL    AND group_id IS NULL) OR "
        "(scope = 'group' AND group_id IS NOT NULL AND site_id  IS NULL    AND brand_id IS NULL)",
    )


def downgrade() -> None:
    """Reverse Stage 13 schema changes."""

    # Drop constraint and indexes before altering columns
    op.drop_constraint(
        "ck_user_access_grants_scope_fk_consistency", "user_access_grants"
    )
    op.drop_index("ix_user_access_grants_group_id", table_name="user_access_grants")
    op.drop_index("ix_user_access_grants_brand_id", table_name="user_access_grants")

    op.drop_column("user_access_grants", "group_id")
    op.drop_column("user_access_grants", "brand_id")
    op.drop_column("user_access_grants", "scope")

    # Restore site_id NOT NULL (safe only if all rows have a value — downgrade
    # assumes no brand/group scope grants exist yet)
    op.alter_column("user_access_grants", "site_id", nullable=False)

    op.drop_column("access_profiles", "can_access_portal")
