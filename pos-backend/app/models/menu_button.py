"""SQLAlchemy ORM model for buttons (product or folder) within a menu tab (Stage 23)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MenuButton(Base):
    """
    A graphical tile inside a MenuTab — either a product button or a folder.

    kind='product': resolves to a product by ref code. product_ref is
    deliberately not a foreign key to products.id — the original ask is that
    a button "relate[s] back to the product based on product code", so a
    button keeps working if the underlying product is deleted and recreated
    with the same ref. Publish-time validation
    (menu_builder_service.publish_menu_layout) warns rather than blocks when
    a ref no longer resolves to an active product.

    kind='folder' (Menu Studio redesign, Phase 2): represents a nested
    MenuTab (child_tab_id) instead of a product — tapping it on the POS (or
    clicking its "open" icon in the portal) drills into that tab. A check
    constraint enforces exactly one of product_ref/child_tab_id per kind.

    width/height are the tile's span in the layout's 6-column CSS grid
    (grid-auto-flow: dense packs remaining tiles around it) — no x/y
    coordinates are stored; the browser computes position from span + order.
    color overrides the linked product's category default colour when set.
    """

    __tablename__ = "menu_buttons"
    __table_args__ = (
        CheckConstraint("kind IN ('product', 'folder')", name="ck_menu_buttons_kind_valid"),
        CheckConstraint("width BETWEEN 1 AND 6", name="ck_menu_buttons_width_range"),
        CheckConstraint("height BETWEEN 1 AND 4", name="ck_menu_buttons_height_range"),
        CheckConstraint(
            "(kind = 'product' AND product_ref IS NOT NULL AND child_tab_id IS NULL) OR "
            "(kind = 'folder' AND child_tab_id IS NOT NULL AND product_ref IS NULL)",
            name="ck_menu_buttons_kind_fields_consistency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    tab_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("menu_tabs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent tab this button belongs to",
    )
    kind: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="product",
        comment="'product' (resolves via product_ref) or 'folder' (opens child_tab_id)",
    )
    product_ref: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Product's ref code (e.g. PRD-000001) — not a FK, see class docstring. Set only when kind='product'",
    )
    child_tab_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("menu_tabs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="The nested tab this folder opens. Set only when kind='folder'",
    )
    width: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Grid column span (1-6)",
    )
    height: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Grid row span (1-4)",
    )
    color: Mapped[str | None] = mapped_column(
        String(7),
        nullable=True,
        comment="Hex colour (#RRGGBB) override; NULL derives from the linked product's category default colour",
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Order buttons are shown in within the tab — lower values appear first",
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
