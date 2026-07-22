"""SQLAlchemy ORM model for table maps (Android POS Phase 4 — table maps & floor service)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TableMap(Base):
    """
    A single floor/map of a site's front-of-house — README-tables-floormap.md's
    "floor" concept (e.g. 'Ground Floor', 'Rooftop'), generalized here to any
    number of maps per site rather than a fixed 'main'/'rooftop' pair.

    Unlike MenuLayout's brand-wide-or-site scope, a table map is always tied
    to exactly one site — a floor plan is a physical space, not something
    that can be reused brand-wide. site_id is therefore required and
    non-nullable, and sort_order (not a scope/default flag) drives the
    portal/Android floor-tab ordering.

    is_active is a soft-delete flag: delete_table_map() sets it False rather
    than hard-deleting the row (mirroring the spec's "keep history" intent
    for the live status layer — see TableSession's docstring — even though
    MenuLayout itself hard-deletes; the two entities' history requirements
    differ so the same convention isn't reused verbatim). Soft-deleted maps
    are excluded from list_table_maps() and the POS read contract by default.

    grid_size/is_grid_locked back the portal's lockable snap-to-grid canvas;
    they are authoring-only (never read by the POS contract).
    """

    __tablename__ = "table_maps"

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
        comment="Denormalized from site_id's brand for brand-scoped portal queries",
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The site this floor plan belongs to — table maps are always site-scoped, never brand-wide",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Floor label shown on the portal editor and Android floor tabs, e.g. 'Ground Floor'",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Order maps are shown in (floor tab order) — lower values appear first",
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether this map's authored layout is live for the POS to render",
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of the most recent publish, if ever published",
    )
    grid_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=20,
        comment="Snap-to-grid unit (percent-of-stage divisions) for the portal editor's canvas",
    )
    is_grid_locked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True — the portal editor's grid snap is locked on; shapes always snap to grid_size",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Soft-delete flag — False means the map is archived, not physically removed",
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
