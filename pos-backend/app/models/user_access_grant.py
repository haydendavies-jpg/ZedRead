"""SQLAlchemy ORM model for POS user access grants linking users to sites, brands, or groups."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserAccessGrant(Base):
    """
    Links a POS user to a site, brand, or group with a specific access profile.

    A grant says: "this user may use this scope with these permissions."
    The `scope` field controls which FK is populated:
      - scope='site'  → site_id is set; brand_id and group_id are NULL
      - scope='brand' → brand_id is set; site_id and group_id are NULL
      - scope='group' → group_id is set; site_id and brand_id are NULL

    A check constraint enforces this at the DB level.
    Multiple grants per user are allowed. Grants are soft-deleted via is_active
    rather than hard-deleted so the audit trail is preserved.

    granted_by_id is nullable so that system-created grants (e.g. during
    invite acceptance) can set it to None before the actor is known.
    """

    __tablename__ = "user_access_grants"
    __table_args__ = (
        # Ensure exactly one scope FK is set and matches the scope field
        CheckConstraint(
            "(scope = 'site'  AND site_id  IS NOT NULL AND brand_id IS NULL    AND group_id IS NULL) OR "
            "(scope = 'brand' AND brand_id IS NOT NULL AND site_id  IS NULL    AND group_id IS NULL) OR "
            "(scope = 'group' AND group_id IS NOT NULL AND site_id  IS NULL    AND brand_id IS NULL)",
            name="ck_user_access_grants_scope_fk_consistency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pos_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The POS user being granted access",
    )
    scope: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="site",
        comment="Scope of this grant: 'site', 'brand', or 'group'",
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Set when scope='site' — the site this grant covers",
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Set when scope='brand' — the brand this grant covers",
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Set when scope='group' — the group this grant covers",
    )
    access_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("access_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        comment="The access profile (permission tier) for this grant",
    )
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pos_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="The POS user who created this grant, or NULL for system grants",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when the grant has been revoked",
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True for the user's primary/default site grant; auto-set on first grant creation",
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
