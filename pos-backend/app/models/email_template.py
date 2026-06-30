"""SQLAlchemy ORM model for SuperAdmin-managed email templates."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EmailTemplate(Base):
    """
    A reusable, admin-editable email template keyed by a stable template_key.

    Bodies use stdlib string.Template `$variable` placeholders (e.g.
    $entity_name, $entity_type) — never arbitrary code, since templates are
    stored data rather than logic. System templates (is_system=True) are
    seeded by migration and cannot be deleted, mirroring AccessProfile's
    is_system protection for the Uncategorised category.
    """

    __tablename__ = "email_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    template_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        comment="Stable identifier looked up by feature code, e.g. 'billing_info_request'",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Admin-facing display name shown in the Email Templates list",
    )
    subject: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Email subject line, may contain $variable placeholders",
    )
    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Email body, may contain $variable placeholders",
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True for seeded templates that cannot be deleted",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False disables this template from being sendable",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
