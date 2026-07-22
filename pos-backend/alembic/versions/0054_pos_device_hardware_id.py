"""Hardware-anchored device recognition — pos_devices.hardware_id.

device_token alone can't survive an app reinstall: it's a server-issued
secret persisted in the app's own storage, which is wiped on uninstall,
so a reinstalled terminal previously looked like a brand-new device and
silently claimed a fresh license seat. hardware_id is a stable
OS-level identifier (Android's Settings.Secure.ANDROID_ID) captured at
first claim, threaded through pos_auth_service so a terminal that lost
its device_token but still reports the same hardware_id is recognised
and re-linked to its existing PosDevice row instead of consuming a new
seat. Deliberately not MAC address: modern Android randomizes the MAC
per network for privacy and blocks apps from reading the real hardware
MAC without root, so it would never reliably match across reinstalls.

Revision ID: 0054
Revises: 0053
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add pos_devices.hardware_id, nullable and unique (existing rows are unknown)."""
    op.add_column(
        "pos_devices",
        sa.Column(
            "hardware_id",
            sa.String(length=255),
            nullable=True,
            unique=True,
            comment="Stable OS-level hardware identifier (Android ID) — recognises a returning physical device across app reinstalls, when device_token itself has been wiped",
        ),
    )


def downgrade() -> None:
    """Drop pos_devices.hardware_id."""
    op.drop_column("pos_devices", "hardware_id")
