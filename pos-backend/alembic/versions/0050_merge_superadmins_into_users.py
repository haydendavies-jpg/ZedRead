"""Merge superadmins into users — SuperAdmin becomes a role on User.

Per the user's request to condense the SuperAdmin/User split: `superadmins`
is no longer a separate identity table. `users.superadmin_role` (nullable,
'admin'|'reseller_staff') is the new orthogonal axis — a User row may carry
tenant scope/grants, a superadmin_role, or (a "hybrid" account) both at once.
`users.group_id` becomes nullable to allow a pure ZedRead/reseller-staff row
with no tenant at all.

Existing `superadmins` rows are migrated as new `users` rows (same `id`, so
`groups.created_by_id` keeps resolving without rewriting data) rather than
attempting to coalesce them into any existing `users` row with the same
email — `users.email` is already non-unique (migration 0031) specifically to
support multiple rows sharing an email, so this is a direct extension of
that existing pattern. Migrated rows keep their historical `PTL-xxxxxx` ref
string as-is; new superadmin_role rows created after this migration get a
normal `USR-xxxxxx` ref from `users_ref_seq` like any other user.

Revision ID: 0050
Revises: 0049
Create Date: 2026-07-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add users.superadmin_role, relax users.group_id, migrate superadmins rows, drop superadmins."""
    # users.superadmin_role — orthogonal axis, NULL means no admin-portal access
    op.add_column(
        "users",
        sa.Column(
            "superadmin_role",
            sa.String(50),
            nullable=True,
            comment="Admin-portal role ('admin'|'reseller_staff'). NULL means no SuperAdmin-tier access.",
        ),
    )

    # users.group_id becomes optional — NULL for a pure ZedRead/reseller-staff row
    op.alter_column("users", "group_id", nullable=True)

    # Belt-and-braces: migration 0031 dropped every unique constraint/index on
    # users.email it knew about (pos_users_email_key/users_email_key,
    # ix_users_email/ix_pos_users_email), but a database provisioned with
    # SQLAlchemy's default naming convention ends up with a constraint named
    # uq_pos_users_email instead — a variant 0031 didn't anticipate, so it
    # silently survived untouched. Nothing hit it until now: this is the first
    # migration that inserts two users rows sharing an email. Drop it here too
    # so the INSERT below (and any future shared-email insert) doesn't 23505.
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_pos_users_email")

    # Migrate each superadmins row into users as a new, separate row (same id,
    # no tenant scope, no grants) — preserves groups.created_by_id resolution
    # and the historical PTL- ref string without renumbering.
    op.execute(
        """
        INSERT INTO users (
            id, group_id, brand_id, ref, first_name, last_name, name, email,
            password_hash, backend_role, superadmin_role, is_active,
            token_version, is_pos_multi_site_enabled, is_master_user,
            created_at, updated_at, password_reset_token, password_reset_token_expires_at
        )
        SELECT
            id, NULL, NULL, ref, NULL, NULL, name, email,
            password_hash, NULL, role, is_active,
            token_version, false, false,
            created_at, updated_at, password_reset_token, password_reset_token_expires_at
        FROM superadmins
        """
    )

    # Re-point groups.created_by_id from superadmins.id to users.id — ids were
    # preserved by the INSERT above, so existing FK values still resolve.
    op.drop_constraint("fk_groups_created_by_id_superadmins", "groups", type_="foreignkey")
    op.create_foreign_key(
        "fk_groups_created_by_id_users",
        "groups",
        "users",
        ["created_by_id"],
        ["id"],
    )

    # user_access_grants.granted_by_id and user_invites.invited_by_id also FK
    # to superadmins in the deployed schema — undocumented drift from the
    # models (which have always declared ForeignKey("users.id", ...)) and
    # from migration 0005 (which created them against pos_users). Wherever
    # they actually came from, DROP TABLE superadmins below fails without
    # re-pointing these too; same id-preservation as groups.created_by_id
    # above means existing values still resolve once re-pointed.
    op.execute(
        "ALTER TABLE user_access_grants DROP CONSTRAINT IF EXISTS user_access_grants_granted_by_id_fkey"
    )
    op.create_foreign_key(
        "user_access_grants_granted_by_id_fkey",
        "user_access_grants",
        "users",
        ["granted_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        "ALTER TABLE user_invites DROP CONSTRAINT IF EXISTS user_invites_invited_by_id_fkey"
    )
    op.create_foreign_key(
        "user_invites_invited_by_id_fkey",
        "user_invites",
        "users",
        ["invited_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_table("superadmins")
    op.execute("DROP SEQUENCE IF EXISTS superadmins_ref_seq")


def downgrade() -> None:
    """Recreate superadmins, copy superadmin_role rows back out, restore users.group_id NOT NULL."""
    op.execute("CREATE SEQUENCE IF NOT EXISTS superadmins_ref_seq")
    op.create_table(
        "superadmins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ref",
            sa.String(20),
            nullable=False,
            unique=True,
            server_default=sa.text("'PTL-' || LPAD(nextval('superadmins_ref_seq')::text, 6, '0')"),
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="admin"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("password_reset_token", sa.String(255), nullable=True),
        sa.Column("password_reset_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_superadmins_email", "superadmins", ["email"], unique=True)
    op.create_index(
        "ix_superadmins_password_reset_token", "superadmins", ["password_reset_token"], unique=True
    )
    op.create_index("ix_superadmins_is_active", "superadmins", ["is_active"])
    op.create_index("ix_superadmins_role", "superadmins", ["role"])

    # Copy every superadmin_role row back out (covers both pure and hybrid
    # rows — a hybrid row's tenant identity stays in `users` too, so its id
    # ends up in both tables, which is fine: they're independent PK spaces).
    op.execute(
        """
        INSERT INTO superadmins (
            id, ref, email, password_hash, name, role, is_active,
            token_version, created_at, updated_at, password_reset_token,
            password_reset_token_expires_at
        )
        SELECT
            id, ref, email, password_hash, name, superadmin_role, is_active,
            token_version, created_at, updated_at, password_reset_token,
            password_reset_token_expires_at
        FROM users
        WHERE superadmin_role IS NOT NULL
        """
    )

    op.drop_constraint("fk_groups_created_by_id_users", "groups", type_="foreignkey")
    op.create_foreign_key(
        "fk_groups_created_by_id_superadmins",
        "groups",
        "superadmins",
        ["created_by_id"],
        ["id"],
    )

    # Only pure ex-superadmin rows (no tenant scope) are removed from users —
    # a hybrid row's tenant identity must remain.
    op.execute("DELETE FROM users WHERE superadmin_role IS NOT NULL AND group_id IS NULL")

    op.alter_column("users", "group_id", nullable=False)
    op.drop_column("users", "superadmin_role")
