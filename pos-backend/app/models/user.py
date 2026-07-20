"""SQLAlchemy ORM model for Users (staff who log into the POS terminal)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    """
    A User is a member of staff who logs into the Android POS terminal.

    Always has POS access; backend/portal access is optional and granted
    per scope via UserAccessGrant. A tenant-scoped User belongs to a Group
    (group_id set); brand_id is additionally set for brand- and site-scoped
    users and is NULL for a Group-level Master User. A pure ZedRead/reseller
    admin-portal row (superadmin_role set, no tenant) has group_id NULL too.
    They authenticate via email+password for initial login and via PIN for
    quick session switching at the terminal.

    Exactly one User per site, per brand, and per group is the immutable
    Master User (is_master_user=True), auto-created alongside its entity —
    see site_service.create_site(), brand_service.create_brand(), and
    group_service.create_group().

    Required-field rules (ROLE_MODEL.md §2): every non-Master User must have
    first_name/last_name (Master User has neither — its `name` is the site's
    name, see site_service._create_master_user()). email/password_hash are
    nullable here and only required at the point a grant is given a
    backend_role — see access_grant_service.update_grant().

    `superadmin_role` is an orthogonal axis to tenant scope/grants (ROLE_MODEL.md
    §1): a User with this set can log into the admin portal with ZedRead/reseller
    staff authority, independent of — and possibly alongside — any Group/Brand/Site
    grants the same row also holds. A pure ZedRead/reseller-staff row (no tenant
    at all) has `group_id=NULL`; a hybrid row (both a tenant identity and portal
    admin) keeps its `group_id` set. This column replaced the standalone
    `SuperAdmin` model/`superadmins` table (see migration 0050) — SuperAdmin
    access is now just a role on User, not a separate identity type.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Parent group for a tenant-scoped user; brand_id is additionally set for brand- and site-scoped users. NULL for a pure ZedRead/reseller-staff row (superadmin_role set, no tenant scope).",
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
        nullable=True,
        index=True,
        comment="Login email. Required once any grant has a backend_role. Non-unique — the same person may manage multiple entities as master user.",
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
    # ZedRead/reseller admin-portal role — orthogonal to group_id/backend_role/grants.
    # Values from SuperAdminRole ('admin' | 'reseller_staff'); NULL = not a portal admin.
    superadmin_role: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Admin-portal role ('admin'|'reseller_staff'). NULL means this User has no SuperAdmin-tier portal access.",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when the user is suspended and cannot log in",
    )
    # Bumped to invalidate all previously issued management tokens for this user
    # (logout-everywhere / password change). Tokens carry the value they were
    # minted with; a mismatch against this column rejects the token.
    token_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Monotonic counter; a token whose 'tv' claim != this is revoked",
    )
    is_pos_multi_site_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment=(
            "'POS - Site Assignment' — when true and the user has active grants "
            "on more than one site, POS login presents a site selector instead "
            "of resolving straight to the device's paired site."
        ),
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
    # Single-use token for the forgot-password flow; NULL when no reset is pending.
    password_reset_token: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    password_reset_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
