"""Add human-readable reference IDs to all major entities.

Each entity type gets a dedicated PostgreSQL sequence and a ref column
(e.g. GRO-000001, BRA-000001, SIT-000001) displayed in the portal UI
instead of raw UUIDs. Internal primary keys remain UUIDs — no FK rewrites
needed, and the portal API continues to accept UUIDs in path/query params.

The server_default expression auto-fills ref on INSERT so application code
never needs to set it explicitly. Existing rows are back-filled in order
of creation (id is a time-ordered UUID v4 approximation, so ordering by
created_at gives a stable result).

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

# (table, sequence_name, prefix)
_ENTITIES = [
    ("groups",        "groups_ref_seq",        "GRO"),
    ("brands",        "brands_ref_seq",        "BRA"),
    ("sites",         "sites_ref_seq",         "SIT"),
    ("pos_users",     "pos_users_ref_seq",     "USR"),
    ("portal_users",  "portal_users_ref_seq",  "PTL"),
    ("products",      "products_ref_seq",      "PRD"),
    ("categories",    "categories_ref_seq",    "CAT"),
    ("tax_categories","tax_categories_ref_seq","TAX"),
    ("licenses",      "licenses_ref_seq",      "LIC"),
]


def upgrade() -> None:
    """Create per-entity sequences and ref columns; back-fill existing rows."""

    for table, seq, prefix in _ENTITIES:
        # 1. Sequence
        op.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} START 1 INCREMENT 1")

        # 2. Nullable column first (required before back-fill)
        op.add_column(
            table,
            sa.Column(
                "ref",
                sa.String(20),
                nullable=True,
                comment=f"Human-readable reference ID, e.g. {prefix}-000001",
            ),
        )

        # 3. Back-fill existing rows ordered by creation time for stable assignment
        op.execute(
            f"""
            WITH ordered AS (
                SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id) AS rn
                FROM {table}
            )
            UPDATE {table}
            SET ref = '{prefix}-' || LPAD(
                (SELECT rn FROM ordered WHERE ordered.id = {table}.id)::text,
                6, '0'
            )
            WHERE ref IS NULL
            """
        )

        # 4. Make NOT NULL now that all rows have a value
        op.alter_column(table, "ref", nullable=False)

        # 5. Server default for future INSERTs
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN ref "
            f"SET DEFAULT '{prefix}-' || LPAD(nextval('{seq}')::text, 6, '0')"
        )

        # 6. Advance the sequence past the highest back-filled number so future
        #    inserts get a unique value even after multiple back-fills.
        op.execute(
            f"SELECT setval('{seq}', (SELECT COUNT(*) FROM {table}) + 1, false)"
        )

        # 7. Unique constraint
        op.create_unique_constraint(f"uq_{table}_ref", table, ["ref"])


def downgrade() -> None:
    """Drop ref columns and sequences."""

    for table, seq, _ in _ENTITIES:
        op.drop_constraint(f"uq_{table}_ref", table, type_="unique")
        op.drop_column(table, "ref")
        op.execute(f"DROP SEQUENCE IF EXISTS {seq}")
