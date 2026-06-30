"""SQLAlchemy ORM model for Users (staff who log into the POS terminal)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    """
    A User is a member of staff who logs into the Android POS terminal.

    Always has POS access; backend/portal access is optional and granted
    per scope via UserAccessGrant. Every User belongs to a Group; brand_id
    is additionally set for brand- and site-scoped users and is NULL for a
    Group-level Master User. They authenticate via email+password for
    initial login and via PIN for quick session switching at the terminal.

    Exactly one User per site, per brand, and per group is the immutable
    Master User (is_master_user=True), auto-created alongside its entity —
    see site_service.create_site(), brand_service.create_brand(), and
    group_service.create_group().

    Required-field rules (ROLE_MODEL.md §2): every non-Master User must have
    first_name/last_name (Master User has neither — its `name` is the site's
    name, see site_service._create_master_user()). email/password_hash are
    nullable here and only required at the point a grant is given a
    backend_role — see access_grant_service.update_grant().
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Parent group — every user belongs to a group; brand_id is additionally set for brand- and site-scoped users",
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Set for brand- and site-scoped users; NULL for a Group-level Master User",
    )
    ref: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        server_default=text("'USR-' || LPAD(nextval('users_ref_seq')::text, 6, '0')"),
        comment="Human-readable reference ID, e.g. USR-000001",
    )
    first_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Required for every User except Master User (ROLE_MODEL.md)",
    )
    last_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Required for every User except Master User (ROLE_MODEL.md)",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment=(
            "Full display name shown on the terminal. Derived from "
            "first_name + last_name for ordinary Users; for the Master "
            "User this is the site's name and has no first/last source."
        ),
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True,
        comment="Login email. Required once any grant has a backend_role.",
    )
    # Argon2 password hash — never store plaintext (rule 15)
    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Argon2 hash of the user's password. Required alongside email.",
    )
    # Portal/backend access level — separate from POS terminal access profile
    # Values: 'admin' | 'users' | 'reporting'; NULL = no backend/portal access
    backend_role: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Backend/portal access level. NULL means no backend access.",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when the user is suspended and cannot log in",
    )
    is_master_user: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment=(
            "True for the single, immutable site-identity User auto-created "
            "per site (ROLE_MODEL.md Master User role). Cannot be edited, "
            "deactivated, or have its site grant revoked/reassigned."
        ),
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
