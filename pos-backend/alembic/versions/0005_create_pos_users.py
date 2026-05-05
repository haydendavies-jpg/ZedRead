"""Create Stage 7 POS user tables: pos_users, access_profiles, user_access_grants,
user_invites, user_pins, user_pos_sessions.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all 6 Stage 7 tables in dependency order."""

    # 1. pos_users — no FK deps beyond brands (already exists)
    op.create_table(
        "pos_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_pos_users_brand_id", "pos_users", ["brand_id"])
    op.create_index("ix_pos_users_email", "pos_users", ["email"], unique=True)

    # 2. access_profiles — no FK deps beyond brands
    op.create_table(
        "access_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_access_profiles_brand_id", "access_profiles", ["brand_id"])

    # 3. user_access_grants — depends on pos_users, sites, access_profiles
    op.create_table(
        "user_access_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pos_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "access_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("access_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "granted_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pos_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_user_access_grants_user_id", "user_access_grants", ["user_id"])
    op.create_index("ix_user_access_grants_site_id", "user_access_grants", ["site_id"])

    # 4. user_invites — depends on brands, sites, access_profiles, pos_users
    op.create_table(
        "user_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "access_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("access_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "invited_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pos_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("token", sa.String(255), nullable=False, unique=True),
        sa.Column("is_accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_user_invites_brand_id", "user_invites", ["brand_id"])
    op.create_index("ix_user_invites_email", "user_invites", ["email"])
    op.create_index("ix_user_invites_token", "user_invites", ["token"], unique=True)

    # 5. user_pins — depends on pos_users; one-to-one (unique on user_id)
    op.create_table(
        "user_pins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pos_users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("pin_hash", sa.String(255), nullable=False),
        sa.Column(
            "is_pin_reset_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # 6. user_pos_sessions — depends on pos_users, sites
    op.create_table(
        "user_pos_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pos_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_jti", sa.String(36), nullable=False, unique=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_user_pos_sessions_user_id", "user_pos_sessions", ["user_id"])
    op.create_index("ix_user_pos_sessions_site_id", "user_pos_sessions", ["site_id"])
    op.create_index(
        "ix_user_pos_sessions_token_jti", "user_pos_sessions", ["token_jti"], unique=True
    )


def downgrade() -> None:
    """Drop all 6 Stage 7 tables in reverse dependency order."""
    op.drop_table("user_pos_sessions")
    op.drop_table("user_pins")
    op.drop_table("user_invites")
    op.drop_table("user_access_grants")
    op.drop_table("access_profiles")
    op.drop_table("pos_users")
