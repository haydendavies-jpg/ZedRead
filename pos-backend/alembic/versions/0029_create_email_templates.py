"""Create email_templates and seed the billing_info_request system template.

A generic, SuperAdmin-managed email template system. Open-ended by design —
new template_key values can be added later via the admin UI without a schema
change, the same way PAGE_CATALOG grows without migrations. The first
consumer is the "request billing info" action on Group/Brand/Site detail
pages, which emails the entity's effective billing contact using the
$entity_name/$entity_type placeholders (stdlib string.Template substitution,
not a templating engine — admins are trusted but we still don't want
arbitrary logic embedded in a DB-stored string).

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-30
"""

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

_BILLING_INFO_REQUEST_KEY = "billing_info_request"
_BILLING_INFO_REQUEST_SUBJECT = "Action needed: billing details for $entity_name"
_BILLING_INFO_REQUEST_BODY = (
    "Hi,\n\n"
    "We're missing billing information for $entity_name ($entity_type). "
    "Please reply to this email with your billing contact and tax details "
    "so we can keep your ZedRead subscription invoicing up to date.\n\n"
    "Thanks,\nZedRead Billing"
)


def upgrade() -> None:
    """Create email_templates and seed the billing_info_request system row."""
    op.create_table(
        "email_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("template_key", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    email_templates = sa.table(
        "email_templates",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("template_key", sa.String),
        sa.column("name", sa.String),
        sa.column("subject", sa.String),
        sa.column("body", sa.Text),
        sa.column("is_system", sa.Boolean),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        email_templates,
        [
            {
                "id": uuid.uuid4(),
                "template_key": _BILLING_INFO_REQUEST_KEY,
                "name": "Billing Info Request",
                "subject": _BILLING_INFO_REQUEST_SUBJECT,
                "body": _BILLING_INFO_REQUEST_BODY,
                "is_system": True,
                "is_active": True,
            }
        ],
    )


def downgrade() -> None:
    """Drop the email_templates table."""
    op.drop_table("email_templates")
