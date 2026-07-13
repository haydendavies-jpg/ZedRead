"""SQLAlchemy ORM model for Menus — a saved, schedulable configuration."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Menu(Base):
    """
    A named, schedulable configuration distinct from a MenuLayout.

    A MenuLayout is the button arrangement; a Menu is what gets assigned to
    registers/channels and published on its own schedule — it optionally
    points at the MenuLayout it activates. scope/site_id reuse the same
    brand-vs-site assignment convention as MenuLayout (see that model's
    docstring) — sites are the closest existing stand-in for a POS
    "register"/"channel"; no dedicated register entity exists yet.
    """

    __tablename__ = "menus"
    __table_args__ = (
        CheckConstraint(
            "(scope = 'site' AND site_id IS NOT NULL) OR (scope = 'brand' AND site_id IS NULL)",
            name="ck_menus_scope_site_consistency",
        ),
        CheckConstraint("status IN ('draft', 'scheduled', 'published')", name="ck_menus_status_valid"),
    )

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
        server_default=text("'MNU-' || LPAD(nextval('menus_ref_seq')::text, 6, '0')"),
        comment="Human-readable reference ID, e.g. MNU-000001",
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent brand — menus are not shared across brands",
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Set only when scope='site' — a site-specific menu",
    )
    scope: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="'brand' (all sites) or 'site' (this site_id only)",
    )
    menu_layout_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("menu_layouts.id", ondelete="SET NULL"),
        nullable=True,
        comment="POS button layout this menu activates, if any",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Display name shown in the portal's Menus page",
    )
    note: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Short freeform note, e.g. daypart or purpose",
    )
    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="draft",
        comment="'draft' | 'scheduled' | 'published'",
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Set when status='scheduled' — when the scheduled publish should fire",
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of the most recent publish, if ever published",
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
