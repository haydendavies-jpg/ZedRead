"""Stage 22 — Variants & Combos portal pages: ref codes, display_name, and
combo group soft-delete support.

Variants (product_variants) and Combos (product_combo_groups — the only
combo-specific entity distinct from Product; a "combo product" is just a
regular Product that owns one or more of these groups) each get a
human-readable ref sequence (VAR-000001 / CMB-000001, same mechanism as
migration 0013) and a nullable display_name the portal shows in place of the
internal name/attribute-derived label when set.

product_combo_groups also gains is_active, bringing it to parity with
product_variants' existing soft-delete flag so both entities support the
same status-toggle table UX as Products (Stage 20).

Revision ID: 0039
Revises: 0038
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add ref/display_name to product_variants and product_combo_groups; is_active on the latter."""
    op.execute("CREATE SEQUENCE IF NOT EXISTS product_variants_ref_seq START 1 INCREMENT 1")
    op.add_column(
        "product_variants",
        sa.Column(
            "ref",
            sa.String(20),
            nullable=False,
            unique=True,
            server_default=sa.text("'VAR-' || LPAD(nextval('product_variants_ref_seq')::text, 6, '0')"),
            comment="Human-readable reference ID, e.g. VAR-000001",
        ),
    )
    op.add_column(
        "product_variants",
        sa.Column(
            "display_name",
            sa.String(255),
            nullable=True,
            comment="Management-facing label distinct from the attribute-derived internal name",
        ),
    )

    op.execute("CREATE SEQUENCE IF NOT EXISTS product_combo_groups_ref_seq START 1 INCREMENT 1")
    op.add_column(
        "product_combo_groups",
        sa.Column(
            "ref",
            sa.String(20),
            nullable=False,
            unique=True,
            server_default=sa.text("'CMB-' || LPAD(nextval('product_combo_groups_ref_seq')::text, 6, '0')"),
            comment="Human-readable reference ID, e.g. CMB-000001",
        ),
    )
    op.add_column(
        "product_combo_groups",
        sa.Column(
            "display_name",
            sa.String(255),
            nullable=True,
            comment="Management-facing label distinct from the POS-facing internal name",
        ),
    )
    op.add_column(
        "product_combo_groups",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="False when soft-deleted — same convention as product_variants.is_active",
        ),
    )


def downgrade() -> None:
    """Remove the Stage 22 columns and ref sequences."""
    op.drop_column("product_combo_groups", "is_active")
    op.drop_column("product_combo_groups", "display_name")
    op.drop_column("product_combo_groups", "ref")
    op.execute("DROP SEQUENCE IF EXISTS product_combo_groups_ref_seq")

    op.drop_column("product_variants", "display_name")
    op.drop_column("product_variants", "ref")
    op.execute("DROP SEQUENCE IF EXISTS product_variants_ref_seq")
