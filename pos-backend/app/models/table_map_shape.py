"""SQLAlchemy ORM model for shapes placed on a table map (Android POS Phase 4)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.table_map import SHAPE_KINDS
from app.database import Base


class TableMapShape(Base):
    """
    One placed shape on a TableMap — either a seatable table (kind in
    TABLE_SHAPE_KINDS: stool/round/rect) or a decorative, non-seatable shape
    used only to render the floor plan's backdrop (kind in DECOR_SHAPE_KINDS:
    zone/bar_counter/entrance/wall — see app.constants.table_map).

    Only table-kind shapes get a 1:1 DiningTable row (created alongside the
    shape in table_map_service.create_table_map_shape) — decorative shapes
    never carry live occupancy status. kind is treated as immutable after
    creation (no update path changes it): switching a shape between
    seatable/decorative would require deciding what happens to any live
    session on its DiningTable, which the "authored on portal, device only
    renders" split described in the build plan doesn't call for — delete and
    recreate the shape instead if a genuine kind change is needed.

    x/y/w/h are percentages of the map's stage (0-100), matching
    README-tables-floormap.md's positioning model for both zones (x/y/w/h)
    and tables (x/y, with the shape kind implying a fixed tile size in the
    reference design). Tables are given their own w/h here too rather than
    relying on kind-implied defaults, for future resize flexibility — the
    same choice menu_buttons made with explicit width/height instead of a
    shape-implied size.

    color is a nullable hex override; decorative zones use it as their tint
    fill, table shapes use it as an accent (falls back to a neutral default
    when unset, resolved by the portal/Android renderer, not this schema).
    dashed marks an outdoor zone's dashed border (README: "Patio", "Deck").
    is_locked is per-shape (distinct from TableMap.is_grid_locked, which
    locks the whole canvas's snap behaviour).
    """

    __tablename__ = "table_map_shapes"
    __table_args__ = (
        CheckConstraint(
            "kind IN (" + ", ".join(f"'{k}'" for k in sorted(SHAPE_KINDS)) + ")",
            name="ck_table_map_shapes_kind_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    table_map_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("table_maps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent map this shape is placed on",
    )
    kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Shape kind — see app.constants.table_map.SHAPE_KINDS; immutable after creation",
    )
    label: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Displayed label — a table code (e.g. 'T3') or a zone name (e.g. 'Patio')",
    )
    x: Mapped[float] = mapped_column(Float, nullable=False, comment="Left position, percent of stage width (0-100)")
    y: Mapped[float] = mapped_column(Float, nullable=False, comment="Top position, percent of stage height (0-100)")
    w: Mapped[float] = mapped_column(Float, nullable=False, comment="Width, percent of stage width (0-100)")
    h: Mapped[float] = mapped_column(Float, nullable=False, comment="Height, percent of stage height (0-100)")
    color: Mapped[str | None] = mapped_column(
        String(7),
        nullable=True,
        comment="Hex colour (#RRGGBB) — zone tint or table accent; NULL falls back to a renderer default",
    )
    is_locked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Per-shape position/size lock, distinct from the map's canvas-wide grid lock",
    )
    dashed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True for an outdoor zone's dashed border (README: Patio/Deck)",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Z-index / draw order among a map's shapes — lower values draw first (underneath)",
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
