"""SQLAlchemy ORM model for modifier "comboing" — an option that expands into a linked group."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ModifierOptionGroupLink(Base):
    """
    Links a ModifierOption to another ModifierGroup it expands into on the POS
    (the "comboing" interaction — picking this option surfaces a nested
    modifier group, e.g. a "Combo" option on a burger surfacing a "Choose a
    side" group).

    Self-referential through modifier_groups. The portal only renders one
    level of nesting today, but nothing here stops a linked group's own
    options from carrying further links — deeper nesting needs no schema
    change, only UI/API support.
    """

    __tablename__ = "modifier_option_group_links"
    __table_args__ = (
        UniqueConstraint("modifier_option_id", "linked_group_id", name="uq_modifier_option_group_links_option_group"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    modifier_option_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modifier_options.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The option that, when selected, expands into linked_group_id",
    )
    linked_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modifier_groups.id", ondelete="CASCADE"),
        nullable=False,
        comment="The modifier group this option links to",
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Order linked groups are shown in under the option — lower values appear first",
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
