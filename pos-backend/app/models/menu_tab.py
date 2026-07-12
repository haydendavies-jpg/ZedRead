"""SQLAlchemy ORM model for menu tabs within a POS menu layout (Stage 23)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MenuTab(Base):
    """
    A single-level tab within a MenuLayout, holding an ordered set of buttons.

    Prototype scope: tabs cannot nest — a tab holds MenuButton rows only.
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
        comment="Parent layout this tab belongs to",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Tab label shown on the POS, e.g. 'Burgers', 'Drinks'",
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
