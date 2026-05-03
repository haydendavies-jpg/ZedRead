"""create_groups_brands_sites_audit_logs

Revision ID: 0001
Revises:
Create Date: 2025-05-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the four foundation tables: groups, brands, sites, audit_logs."""

    op.create_table(
        "groups",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            comment="Primary key — UUID generated at insert time",
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="False when the group is suspended",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "brands",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("groups.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_brands_group_id", "brands", ["group_id"])

    op.create_table(
        "sites",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_sites_brand_id", "sites", ["brand_id"])

    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        # Actor fields
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Null for system-generated audit rows (Celery tasks etc.)",
        ),
        sa.Column(
            "actor_type",
            sa.String(20),
            nullable=False,
            comment="'user' or 'system'",
        ),
        sa.Column(
            "actor_email",
            sa.String(255),
            nullable=True,
            comment="Snapshotted at time of action",
        ),
        sa.Column(
            "actor_name",
            sa.String(255),
            nullable=True,
            comment="Snapshotted at time of action",
        ),
        # Action fields
        sa.Column(
            "action",
            sa.String(100),
            nullable=False,
            comment="Dot-separated action constant, e.g. 'group.created'",
        ),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column(
            "entity_id",
            sa.String(100),
            nullable=False,
            comment="String-cast PK of the affected row",
        ),
        # State snapshot
        sa.Column("before_state", postgresql.JSONB(), nullable=True),
        sa.Column("after_state", postgresql.JSONB(), nullable=True),
        # Request correlation
        sa.Column(
            "request_id",
            sa.String(36),
            nullable=True,
            comment="UUID from X-Request-ID — links this row to the HTTP request",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # Index for looking up all audit rows for a specific entity
    op.create_index(
        "ix_audit_logs_entity",
        "audit_logs",
        ["entity_type", "entity_id"],
    )
    # Index for filtering by actor
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    # Index for filtering by action type
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade() -> None:
    """Drop all four foundation tables in reverse dependency order."""
    op.drop_table("audit_logs")
    op.drop_table("sites")
    op.drop_table("brands")
    op.drop_table("groups")
