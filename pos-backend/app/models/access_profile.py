"""SQLAlchemy ORM model for access profiles controlling User permissions."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AccessProfile(Base):
    """
    Defines a named permission tier for Users within a brand or group.

    Five system profiles (Admin, Reporting Only, Manager, Staff, Master User)
    are seeded automatically when a brand is created — the 5 target roles in
    ROLE_MODEL.md. A single group-scoped Master User profile is additionally
    seeded per group (see access_profile_service.seed_group_master_profile())
    for the group-level Master User; the other four tiers stay brand-only
    since they gate catalog/product permissions that only make sense once a
    Brand exists. Exactly one of brand_id/group_id is set per profile,
    enforced by ck_access_profiles_scope_fk_consistency. Additional custom
    profiles can be created by brand admins. System profiles cannot be
    deleted (is_system=True).
    """

    __tablename__ = "access_profiles"
    __table_args__ = (
        # Ensure exactly one scope FK is set
        CheckConstraint(
            "(brand_id IS NOT NULL AND group_id IS NULL) OR "
            "(brand_id IS NULL AND group_id IS NOT NULL)",
            name="ck_access_profiles_scope_fk_consistency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key — UUID generated at insert time",
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Set for brand-scoped profiles — profiles are not shared across brands",
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Set for the group-scoped Master User profile",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable profile name, e.g. 'Admin', 'Staff'",
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True for the 4 auto-seeded system profiles — these cannot be deleted",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False when the profile is soft-deleted",
    )
    can_access_portal: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True when holders of this profile may log into the management portal",
    )
    can_use_open_item: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True when holders of this profile may sell a product flagged is_open_item "
        "with a freely-entered name/price (Stage 24 capability flag, not a page grant)",
    )
    open_item_max_price_cents: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Optional ceiling on the price a holder may enter for an open item; "
        "NULL means no ceiling",
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
