"""SQLAlchemy ORM model for POS setting overrides (Android POS Phase 2)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SettingValue(Base):
    """
    A brand- or site-level override for one setting key.

    The catalog of valid setting keys (label/category/type/options/default)
    lives in code — app/constants/settings.py — not in this table. A row
    here only exists where a brand or site has actually overridden a
    setting's default; resolution falls back site → brand → catalog default
    (see settings_service.resolve_effective_settings()).

    A brand-level default has site_id NULL; a site-level override has
    site_id set to that site (which must belong to brand_id). Two partial
    unique indexes enforce at most one row per (brand, key) at brand level
    and per (site, key) at site level — a plain composite unique index can't
    express this because Postgres treats every NULL as distinct.
    """

    __tablename__ = "setting_values"
    __table_args__ = (
        Index(
            "uq_setting_values_brand_default",
            "brand_id",
            "setting_key",
            unique=True,
            postgresql_where="site_id IS NULL",
        ),
        Index(
            "uq_setting_values_site_override",
            "site_id",
            "setting_key",
            unique=True,
            postgresql_where="site_id IS NOT NULL",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Brand this override belongs to — set even for a site-level row",
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="NULL for a brand-level default; set for a site-level override",
    )
    setting_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Key from the code-defined catalog in app/constants/settings.py",
    )
    value: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="JSON-wrapped value, e.g. {'value': true} or {'value': 'bulk'} — type validated against the catalog entry's SettingType",
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
