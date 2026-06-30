"""Resolves effective logo and billing-email values for Group/Brand/Site.

logo_url and billing_email inherit down the hierarchy (Group -> Brand ->
Site), with a child's own value taking priority over its parent's. This
is the only inheritance in the company-profile feature — timezone,
currency, and country are required independently at every level and never
fall back to a parent (see the company-profile plan).
"""

from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import BILLING_INFO_REQUESTED
from app.models.brand import Brand
from app.models.group import Group
from app.models.site import Site
from app.models.superadmin import SuperAdmin
from app.services.audit_service import log_action
from app.services.email_template_service import get_template_by_key
from app.utils.email import send_billing_info_request_email

EntityLevel = Literal["site", "brand", "group"]

_BILLING_INFO_REQUEST_TEMPLATE_KEY = "billing_info_request"


@dataclass(frozen=True)
class ResolvedValue:
    """An inherited field's value and the hierarchy level it came from."""

    value: str | None
    source_level: EntityLevel | None


async def _ancestors(db: AsyncSession, site: Site) -> tuple[Brand | None, Group | None]:
    """
    Load a Site's parent Brand and grandparent Group.

    Args:
        db: Active database session.
        site: The site whose ancestors to load.

    Returns:
        tuple[Brand | None, Group | None]: The parent brand and grandparent
        group, or (None, None)/(<brand>, None) if a parent has been deleted
        (should not normally happen — brands/groups are RESTRICT on delete).
    """
    brand_result = await db.execute(select(Brand).where(Brand.id == site.brand_id))
    brand = brand_result.scalar_one_or_none()
    if brand is None:
        return None, None

    group_result = await db.execute(select(Group).where(Group.id == brand.group_id))
    group = group_result.scalar_one_or_none()
    return brand, group


def _resolve_field(
    field: str,
    site: Site | None,
    brand: Brand | None,
    group: Group | None,
) -> ResolvedValue:
    """
    Walk site -> brand -> group, returning the first non-null value for `field`.

    Args:
        field: The attribute name to resolve ('logo_url' or 'billing_email').
        site: The site to resolve from, or None if resolving from brand/group directly.
        brand: The site's parent brand (or the brand being resolved directly).
        group: The brand's parent group (or the group being resolved directly).

    Returns:
        ResolvedValue: The first non-null value found, tagged with its source level.
    """
    if site is not None and getattr(site, field):
        return ResolvedValue(value=getattr(site, field), source_level="site")
    if brand is not None and getattr(brand, field):
        return ResolvedValue(value=getattr(brand, field), source_level="brand")
    if group is not None and getattr(group, field):
        return ResolvedValue(value=getattr(group, field), source_level="group")
    return ResolvedValue(value=None, source_level=None)


async def resolve_effective_logo(db: AsyncSession, entity: Site | Brand | Group) -> ResolvedValue:
    """
    Resolve the effective logo_url for a Site, Brand, or Group.

    Args:
        db: Active database session.
        entity: The Site, Brand, or Group to resolve the logo for.

    Returns:
        ResolvedValue: The effective logo URL and which level it came from.
    """
    if isinstance(entity, Site):
        brand, group = await _ancestors(db, entity)
        return _resolve_field("logo_url", entity, brand, group)
    if isinstance(entity, Brand):
        group_result = await db.execute(select(Group).where(Group.id == entity.group_id))
        group = group_result.scalar_one_or_none()
        return _resolve_field("logo_url", None, entity, group)
    return _resolve_field("logo_url", None, None, entity)


async def resolve_effective_billing_email(
    db: AsyncSession, entity: Site | Brand | Group
) -> ResolvedValue:
    """
    Resolve the effective billing_email for a Site, Brand, or Group.

    Args:
        db: Active database session.
        entity: The Site, Brand, or Group to resolve the billing email for.

    Returns:
        ResolvedValue: The effective billing email and which level it came from.
    """
    if isinstance(entity, Site):
        brand, group = await _ancestors(db, entity)
        return _resolve_field("billing_email", entity, brand, group)
    if isinstance(entity, Brand):
        group_result = await db.execute(select(Group).where(Group.id == entity.group_id))
        group = group_result.scalar_one_or_none()
        return _resolve_field("billing_email", None, entity, group)
    return _resolve_field("billing_email", None, None, entity)


async def request_billing_info(
    db: AsyncSession,
    entity: Site | Brand | Group,
    entity_type: EntityLevel,
    actor: SuperAdmin,
) -> ResolvedValue:
    """
    Resolve the effective billing email for a Site/Brand/Group, send the
    active billing_info_request email template to it, and write an audit log row.

    Args:
        db: Active database session.
        entity: The Site, Brand, or Group to request billing info for.
        entity_type: "site", "brand", or "group" — used for the audit row's
            entity_type and the email template's $entity_type placeholder.
        actor: The authenticated SuperAdmin performing the action.

    Returns:
        ResolvedValue: The billing email sent to and which hierarchy level it came from.

    Raises:
        HTTPException: 409 if no billing email is set anywhere in entity's chain.
        HTTPException: 404 if the billing_info_request email template is missing or inactive.
    """
    resolved = await resolve_effective_billing_email(db, entity)
    if resolved.value is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No billing email is set for this entity or any of its parents",
        )

    template = await get_template_by_key(db, _BILLING_INFO_REQUEST_TEMPLATE_KEY)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The billing_info_request email template is missing or inactive",
        )

    await send_billing_info_request_email(
        to_email=resolved.value,
        entity_name=entity.name,
        entity_type=entity_type,
        subject_template=template.subject,
        body_template=template.body,
    )

    await log_action(
        db=db,
        action=BILLING_INFO_REQUESTED,
        entity_type=entity_type,
        entity_id=str(entity.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"sent_to": resolved.value, "source_level": resolved.source_level},
    )
    await db.commit()

    return resolved
