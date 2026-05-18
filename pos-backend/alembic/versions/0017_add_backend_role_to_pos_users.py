"""Add backend_role to pos_users.

Stores the portal/backend access level for a POS user so it can be set
independently of the POS terminal access profile. Nullable — NULL means
the user has no backend access at all.

Values: 'admin' | 'users' | 'reporting'  (all have full access for now;
permissions will be refined in a future stage).
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add backend_role column to pos_users."""
    op.add_column(
        "pos_users",
        sa.Column(
            "backend_role",
            sa.String(20),
            nullable=True,
            comment="Portal/backend access level: 'admin', 'users', or 'reporting'. NULL = no backend access.",
        ),
    )


def downgrade() -> None:
    """Remove backend_role from pos_users."""
    op.drop_column("pos_users", "backend_role")
