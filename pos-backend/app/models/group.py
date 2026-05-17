"""SQLAlchemy ORM model for the groups table (top of the multi-tenant hierarchy)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Group(Base):
    """
    A Group is the top-level tenant unit.

    One group typically represents a business owner or reseller customer.
    Groups contain one or more Brands.
    """

    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    ref: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        server_default=text("'GRO-' || LPAD(nextval('groups_ref_seq')::text, 6, '0')"),
        comment="Human-readable reference ID, e.g. GRO-000001",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Display name of the group",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when the group is suspended — blocks all child logins",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="UTC timestamp set by the DB on insert",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="UTC timestamp updated by the DB on every write",
    )
