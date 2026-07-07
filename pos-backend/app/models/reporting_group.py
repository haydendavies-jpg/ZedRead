"""SQLAlchemy ORM model for reporting groups.

A ReportingGroup sits one level above Category (brand-scoped, per Stage 16 /
ROADMAP.md Phase 5). Every brand gets one system default group (is_system=True,
is_default=True) auto-created alongside its 'Uncategorised' category; every
Category must belong to exactly one ReportingGroup.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReportingGroup(Base):
    """
    A named grouping of Categories belonging to a Brand, used for sales reporting roll-ups.

    The default group (is_system=True, is_default=True) is auto-created when a
    brand is created and cannot be deleted or unset as default. Categories with
    no explicit reporting group are assigned to it.
    """

    __tablename__ = "reporting_groups"

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
        comment="Parent brand — reporting groups are not shared across brands",
    )
    ref: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        server_default=text("'RPG-' || LPAD(nextval('reporting_groups_ref_seq')::text, 6, '0')"),
        comment="Human-readable reference ID, e.g. RPG-000001",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Display name shown in the portal's Reporting Groups page",
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True for the one auto-seeded group new categories fall back to",
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True for the auto-seeded default group — cannot be deleted",
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

    brand: Mapped["Brand"] = relationship("Brand", back_populates="reporting_groups")  # type: ignore[name-defined]
    categories: Mapped[list["Category"]] = relationship(  # type: ignore[name-defined]
        "Category", back_populates="reporting_group"
    )
