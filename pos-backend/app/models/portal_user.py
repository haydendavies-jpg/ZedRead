"""SQLAlchemy ORM model for portal (super-admin) users."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PortalUser(Base):
    """
    A portal (super-admin) user who can log into the React management portal.

    Role determines which pages and actions are accessible:
    - super_admin: full access including user management
    - admin: hierarchy and license management, no user management
    - reseller: read-only view of their own group hierarchy
    """

    __tablename__ = "portal_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    ref: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        server_default=text("'PTL-' || LPAD(nextval('portal_users_ref_seq')::text, 6, '0')"),
        comment="Human-readable reference ID, e.g. PTL-000001",
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # Argon2 password hash — never store plaintext (rule 15)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Role values defined in PortalUserRole enum in app/constants/statuses.py
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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
