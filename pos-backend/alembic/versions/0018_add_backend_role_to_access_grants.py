"""Add backend_role to user_access_grants table.

Stores portal/backend access level per grant so that access can be
configured independently for each scope (site, brand, group) rather
than globally per user.
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add backend_role column to user_access_grants."""
    op.add_column(
        "user_access_grants",
        sa.Column(
            "backend_role",
            sa.String(20),
            nullable=True,
            comment="Backend/portal access level for this grant. NULL means no backend access.",
        ),
    )


def downgrade() -> None:
    """Remove backend_role column from user_access_grants."""
    op.drop_column("user_access_grants", "backend_role")
