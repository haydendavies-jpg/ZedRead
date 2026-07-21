"""Self-service license-seat device claiming — licenses.max_devices.

Backs the auth rework replacing admin pre-registration of Android POS
terminals with a self-service flow: a POS user logs in, picks a granted
site, and the app itself claims an available seat on that site's license
(see pos_auth_service._resolve_or_claim_device). max_devices is the seat
capacity a claim/re-pair checks against, counted live from active
pos_devices rows rather than a separate counter column.

Revision ID: 0051
Revises: 0050
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add licenses.max_devices, defaulting existing rows to a single seat."""
    op.add_column(
        "licenses",
        sa.Column(
            "max_devices",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Seat capacity — how many active pos_devices this license may claim at once",
        ),
    )


def downgrade() -> None:
    """Drop licenses.max_devices."""
    op.drop_column("licenses", "max_devices")
