"""Add impersonator_id and impersonator_email columns to audit_logs.

When a SuperAdmin impersonates an entity's master user, all actions taken
during that session are logged under the admin's identity (actor_id/email/name
carry the admin's details). These two nullable columns provide an additional
cross-reference: they record the admin's UUID and email so queries can find
all rows where impersonation was active, independent of the actor fields.

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add impersonator_id and impersonator_email to audit_logs."""
    op.add_column(
        "audit_logs",
        sa.Column(
            "impersonator_id",
            UUID(as_uuid=True),
            nullable=True,
            comment="SuperAdmin UUID when this action was taken under impersonation",
        ),
    )
    op.add_column(
        "audit_logs",
        sa.Column(
            "impersonator_email",
            sa.String(255),
            nullable=True,
            comment="Snapshotted admin email when impersonating — preserved for audit trail",
        ),
    )


def downgrade() -> None:
    """Remove impersonator columns from audit_logs."""
    op.drop_column("audit_logs", "impersonator_email")
    op.drop_column("audit_logs", "impersonator_id")
