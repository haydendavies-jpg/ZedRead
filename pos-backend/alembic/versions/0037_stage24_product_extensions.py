"""Stage 24 — product model extensions: print_name, is_open_item, and the
matching open-item capability flags on access_profiles.

products.ref already exists (migration 0013) but was never wired into the
ORM/schema layer until this stage — no column change needed for it here.

Revision ID: 0037
Revises: 0036
Create Date: 2026-07-06
"""

from alembic import op
import sqlalchemy as sa

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add print_name/is_open_item to products and open-item capability flags to access_profiles."""
    op.add_column(
        "products",
        sa.Column(
            "print_name",
            sa.String(255),
            nullable=True,
            comment="Alternative name for production dockets — falls back to name when NULL",
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "is_open_item",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="True → sold with a freely-enterable name/price at sale time",
        ),
    )
    op.add_column(
        "access_profiles",
        sa.Column(
            "can_use_open_item",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="True when holders of this profile may sell an is_open_item product",
        ),
    )
    op.add_column(
        "access_profiles",
        sa.Column(
            "open_item_max_price_cents",
            sa.BigInteger(),
            nullable=True,
            comment="Optional ceiling on the price a holder may enter for an open item",
        ),
    )


def downgrade() -> None:
    """Remove the Stage 24 product extension columns."""
    op.drop_column("access_profiles", "open_item_max_price_cents")
    op.drop_column("access_profiles", "can_use_open_item")
    op.drop_column("products", "is_open_item")
    op.drop_column("products", "print_name")
