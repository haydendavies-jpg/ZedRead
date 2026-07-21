"""SQLAlchemy ORM model for the groups table (top of the multi-tenant hierarchy)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func, text
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
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        comment="User (superadmin_role) who created this group. Scopes Reseller "
        "Staff visibility to own accounts only (ROLE_MODEL.md §5.1); NULL for "
        "pre-existing groups and groups created by Admin.",
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="IANA timezone name, e.g. 'Australia/Sydney'. Required independently per level.",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        comment="ISO 4217 currency code, e.g. 'AUD'. Editing this affects invoice currency.",
    )
    country: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        comment="ISO 3166-1 alpha-2 country code, e.g. 'AU'. Drives the tax ID label.",
    )
    tax_id_value: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Free-text tax identifier (e.g. ABN, NZBN); label resolved from country.",
    )
    logo_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Uploaded logo URL. Inherits down to Brand/Site when unset there.",
    )
    billing_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Billing contact email. Inherits down to Brand/Site when unset there.",
    )
