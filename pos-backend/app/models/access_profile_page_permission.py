"""SQLAlchemy ORM model for per-page permission grants on an AccessProfile."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AccessProfilePagePermission(Base):
    """
    Grants a single portal page to an AccessProfile (ROLE_MODEL.md §4).

    Presence-based: a row means the page is granted, absence means it is
    not. A category tab is visible if any page within it has a row for the
    holder's AccessProfile. page_key is validated against
    app.constants.pages.PAGE_KEYS at the service layer, not by a DB
    constraint, since the catalog is expected to grow over time.
    """

    __tablename__ = "access_profile_page_permissions"
    __table_args__ = (
        UniqueConstraint("access_profile_id", "page_key", name="uq_profile_page"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    access_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("access_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The access profile this page grant belongs to",
    )
    page_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Key from app.constants.pages.PAGE_CATALOG, e.g. 'daily_sales'",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
