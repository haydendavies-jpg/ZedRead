"""Product sold-out flag — products.is_sold_out.

User-testing feedback for the Android Register: pressing and holding a
product tile should pop up a window showing the product's short description
(products.description, already wired since the catalog's first stage) and a
sold-out toggle. Setting it greys the tile out on the POS with "SOLD OUT"
written over it and blocks adding it to an order; toggling it back off is
the same press-and-hold popup. Brand-wide, not per-site — see the model
column's own comment for why.

Revision ID: 0057
Revises: 0056
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add products.is_sold_out, not null, defaulting False for existing rows."""
    op.add_column(
        "products",
        sa.Column(
            "is_sold_out",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="True when the POS should refuse to sell this product — set/cleared from the "
            "Android Register's long-press product popup.",
        ),
    )


def downgrade() -> None:
    """Drop products.is_sold_out."""
    op.drop_column("products", "is_sold_out")
