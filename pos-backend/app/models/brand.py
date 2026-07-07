"""SQLAlchemy ORM model for the brands table (second tier of the multi-tenant hierarchy)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Brand(Base):
    """
    A Brand belongs to a Group and represents a distinct business concept.

    For example, a Group might own two restaurant brands operating under
    different names. Each Brand has its own product catalog, users, and sites.
    """

    __tablename__ = "brands"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Parent group — cannot delete a group while brands exist",
    )
    ref: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        server_default=text("'BRA-' || LPAD(nextval('brands_ref_seq')::text, 6, '0')"),
        comment="Human-readable reference ID, e.g. BRA-000001",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Display name of the brand",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when the brand is suspended",
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
        comment="Uploaded logo URL. Falls back to the parent Group's logo when unset; inherits down to Site.",
    )
    billing_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Billing contact email. Falls back to the parent Group's when unset; inherits down to Site.",
    )

    categories: Mapped[list["Category"]] = relationship(  # type: ignore[name-defined]
        "Category", back_populates="brand", cascade="all, delete-orphan"
    )
    reporting_groups: Mapped[list["ReportingGroup"]] = relationship(  # type: ignore[name-defined]
        "ReportingGroup", back_populates="brand", cascade="all, delete-orphan"
    )
