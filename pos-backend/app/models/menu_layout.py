"""SQLAlchemy ORM model for POS menu layouts (Stage 23 — POS Menu Builder)."""

import uuid
from datetime import datetime, time

from sqlalchemy import ARRAY, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, SmallInteger, String, Time, func
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

    Active-time/day-of-week (is_all_day/start_time/end_time/active_days) is a
    first-class scheduling concept distinct from is_published: it controls
    when a *published* layout is visible on the POS (e.g. a Breakfast layout
    only 7am-11am), not whether the edits themselves are live.
    scheduled_publish_at is the separate "Schedule publish" bulk action (Menu
    Studio redesign, Phase 2) — persisted only; nothing auto-fires it yet
    (same known limitation as the Menus entity's own schedule field).
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
    color: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
        default="#A82040",
        comment="Hex colour (#RRGGBB) for the layout's dot in the layouts list and rail",
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="More than one layout may be published at once (per-site/day-part menus)",
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of the most recent publish, if ever published",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Incremented each time the layout is published",
    )
    is_all_day: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="True — layout is visible on the POS all day; False — restricted to start_time/end_time",
    )
    start_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
        comment="POS visibility window start — set only when is_all_day=False",
    )
    end_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
        comment="POS visibility window end — set only when is_all_day=False",
    )
    active_days: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger),
        nullable=False,
        default=lambda: [0, 1, 2, 3, 4, 5, 6],
        comment="Weekdays the layout is visible on the POS — 0=Monday .. 6=Sunday (date.weekday() convention)",
    )
    scheduled_publish_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="'Schedule publish' bulk action target time — persisted only, see class docstring",
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
