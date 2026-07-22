"""Menu layout scheduled-default flag — menu_layouts.is_default.

Phase 3 (Menu Studio -> POS integration depth) needs exactly one layout to
resolve as the "scheduled/default" choice for a given site at a given time,
distinct from a staff member manually overriding the selection on the
Android menu selector. menu_layouts already carries active-time/day-of-week
scheduling (is_all_day/start_time/end_time/active_days) at the layout level
from Phase 2's grid editor, and a layout's scope ('brand' applies to every
site, 'site' restricts to one) already stands in for the "site assignment"
this column attaches to — no separate assignment table is needed. Uniqueness
(at most one is_default=True per site_id among scope='site' rows, and at
most one per brand_id among scope='brand' rows) is enforced in the service
layer, mirroring UserAccessGrant.is_default's own single-default convention,
not a DB constraint (a partial unique index can't span the two different
scope groupings cleanly).

Revision ID: 0055
Revises: 0054
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add menu_layouts.is_default, not null, defaulting False for existing rows."""
    op.add_column(
        "menu_layouts",
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="True if this is the scheduled/default layout for its scope (brand-wide fallback or a site's own override) — resolved by the POS ahead of any manual override",
        ),
    )


def downgrade() -> None:
    """Drop menu_layouts.is_default."""
    op.drop_column("menu_layouts", "is_default")
