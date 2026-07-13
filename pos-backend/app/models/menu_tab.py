"""SQLAlchemy ORM model for menu tabs within a POS menu layout (Stage 23)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MenuTab(Base):
    """
    A tab within a MenuLayout, holding an ordered set of buttons.

    parent_tab_id is nullable and self-referential: NULL for a top-level tab
    (shown in the layout's rail), set for a nested tab reached by "drilling
    into" a folder-kind MenuButton (Menu Studio redesign, Phase 2 — the
    Stage 23 prototype's "tabs cannot nest" limit is lifted here). Nesting
    depth is unbounded; the portal's breadcrumb is built by walking
    parent_tab_id up to NULL.
    """

    __tablename__ = "menu_tabs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    layout_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("menu_layouts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent layout this tab belongs to (set on every tab, nested or not)",
    )
    parent_tab_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("menu_tabs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="NULL for a top-level (rail) tab; set for a tab nested under a folder button",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Tab label shown on the POS, e.g. 'Burgers', 'Drinks'",
    )
    color: Mapped[str | None] = mapped_column(
        String(7),
        nullable=True,
        comment="Hex colour (#RRGGBB) for the rail dot / folder tile accent; falls back to a default when unset",
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Order tabs are shown in — lower values appear first",
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
