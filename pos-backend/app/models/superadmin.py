"""SQLAlchemy ORM model for portal (super-admin) users."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SuperAdmin(Base):
    """
    A portal (super-admin) user who can log into the React management portal.

    Role determines which pages and actions are accessible:
    - admin: full ZedRead administrative access, sees and manages all Groups
      across all resellers
    - reseller_staff: partner-side staff, scoped to only the Groups they
      personally created or are assigned to
    """

    __tablename__ = "superadmins"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    ref: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        server_default=text("'PTL-' || LPAD(nextval('superadmins_ref_seq')::text, 6, '0')"),
        comment="Human-readable reference ID, e.g. PTL-000001",
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # Argon2 password hash — never store plaintext (rule 15)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Role values defined in SuperAdminRole enum in app/constants/statuses.py
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Bumped to invalidate all previously issued portal tokens for this admin
    # (logout-everywhere / password change/reset). Tokens carry the value they
    # were minted with; a mismatch against this column rejects the token.
    token_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Monotonic counter; a token whose 'tv' claim != this is revoked",
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
    # Single-use token for the forgot-password flow; NULL when no reset is pending
    password_reset_token: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    password_reset_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
