"""SQLAlchemy ORM model for product buttons within a menu tab (Stage 23)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MenuButton(Base):
    """
    A graphical button inside a MenuTab that resolves to a product by ref code.

    product_ref is deliberately not a foreign key to products.id — the
    original ask is that a button "relate[s] back to the product based on
    product code", so a button keeps working if the underlying product is
    deleted and recreated with the same ref. Publish-time validation
    (menu_builder_service.publish_menu_layout) warns rather than blocks when
    a ref no longer resolves to an active product.
    """

    __tablename__ = "menu_buttons"

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
    product_ref: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Product's ref code (e.g. PRD-000001) — not a FK, see class docstring",
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
