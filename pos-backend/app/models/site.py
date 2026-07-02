"""SQLAlchemy ORM model for the sites table (third tier — individual locations)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Site(Base):
    """
    A Site is a physical or virtual location belonging to a Brand.

    Each site runs its own Android POS terminal and has its own inventory
    overrides, user access grants, and license assignment.
    """

    __tablename__ = "sites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Parent brand — cannot delete a brand while sites exist",
    )
    ref: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        server_default=text("'SIT-' || LPAD(nextval('sites_ref_seq')::text, 6, '0')"),
        comment="Human-readable reference ID, e.g. SIT-000001",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Display name of the site (e.g. 'City CBD', 'Airport')",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when the site is suspended",
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
        comment="ISO 3166-1 alpha-2 country code, e.g. 'AU'. Drives the tax ID label and address country.",
    )
    tax_id_value: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Free-text tax identifier (e.g. ABN, NZBN); label resolved from country.",
    )
    logo_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Uploaded logo URL. Falls back to the parent Brand's (then Group's) logo when unset.",
    )
    billing_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Billing contact email. Falls back to the parent Brand's (then Group's) when unset.",
    )
    address_street: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Street address of this physical site.",
    )
    address_city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        server_default="",
        comment="Suburb/city of this physical site.",
    )
    address_state: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="State/territory/province of this site.",
    )
    address_postcode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Postal/zip code of this site.",
    )
