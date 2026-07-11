"""SQLAlchemy ORM model for POS menu layouts (Stage 23 — POS Menu Builder)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MenuLayout(Base):
    """
    A graphical POS menu layout — a named set of tabs, each holding product buttons.

    scope='brand' applies the layout to every site in the brand; scope='site'
    restricts it to a single site_id. More than one layout may have
    is_published=True at the same time (e.g. per-site or day-part menus) — a
    check constraint keeps scope and site_id consistent, the same convention
    used for UserAccessGrant.scope.

    version is incremented on every publish so a consumer (Android, once
    built) can detect a layout has changed since it last cached it.
    """

    __tablename__ = "menu_layouts"
    __table_args__ = (
        CheckConstraint(
            "(scope = 'site' AND site_id IS NOT NULL) OR (scope = 'brand' AND site_id IS NULL)",
            name="ck_menu_layouts_scope_site_consistency",
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
        comment="Parent brand — menu layouts are not shared across brands",
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Set only when scope='site' — a site-specific menu layout",
    )
    scope: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="'brand' (all sites) or 'site' (this site_id only)",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Display name shown in the portal's Menu Builder page",
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="More than one layout may be published at once (per-site/day-part menus)",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Incremented each time the layout is published",
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
