"""Business logic for the POS settings framework (Android POS Phase 2).

Resolution is site → brand → catalog default, mirroring the existing
Group→Brand→Site scoping pattern used by access profiles/licenses (see
CLAUDE.md's "Locked-in architecture decisions"). The catalog of valid
setting keys lives in code (app/constants/settings.py); only overrides are
persisted (app/models/setting_value.py).
"""

import uuid
from typing import Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import SETTING_RESET, SETTING_UPDATED
from app.constants.settings import SettingDefinition, get_setting_definition, search_setting_definitions
from app.constants.statuses import ActorType, SettingType
from app.models.setting_value import SettingValue
from app.models.site import Site
from app.models.user import User
from app.schemas.setting import SettingOut
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


def _validate_value(definition: SettingDefinition, value: Any) -> None:
    """
    Validate a submitted value against its setting's catalog type and options.

    Args:
        definition: The setting's catalog definition.
        value: The value to validate.

    Raises:
        HTTPException: 422 if the value's shape doesn't match the setting's type.
    """
    if definition.type == SettingType.BOOLEAN:
        if not isinstance(value, bool):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Setting '{definition.key}' requires a boolean value",
            )
    elif definition.type == SettingType.DATETIME:
        if not isinstance(value, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Setting '{definition.key}' requires an ISO 8601 datetime string",
            )
    elif definition.type == SettingType.SINGLE_SELECT:
        if not isinstance(value, str) or (definition.options and value not in definition.options):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Setting '{definition.key}' must be one of {definition.options}",
            )
    elif definition.type == SettingType.MULTI_SELECT:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Setting '{definition.key}' requires a list of strings",
            )
        if definition.options and not set(value).issubset(set(definition.options)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Setting '{definition.key}' values must be a subset of {definition.options}",
            )


async def _load_overrides(
    db: AsyncSession, brand_id: uuid.UUID, site_id: uuid.UUID | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Load a brand's setting overrides and (optionally) one site's overrides.

    Args:
        db: Active database session.
        brand_id: Brand to load the brand-level defaults for.
        site_id: Site to load site-level overrides for, or None to skip.

    Returns:
        tuple[dict[str, Any], dict[str, Any]]: (brand_values, site_values),
            each keyed by setting_key with the unwrapped value.
    """
    brand_result = await db.execute(
        select(SettingValue).where(SettingValue.brand_id == brand_id, SettingValue.site_id.is_(None))
    )
    brand_values = {row.setting_key: row.value["value"] for row in brand_result.scalars().all()}

    site_values: dict[str, Any] = {}
    if site_id is not None:
        site_result = await db.execute(
            select(SettingValue).where(SettingValue.site_id == site_id)
        )
        site_values = {row.setting_key: row.value["value"] for row in site_result.scalars().all()}

    return brand_values, site_values


def _build_setting_out(
    definition: SettingDefinition, brand_values: dict[str, Any], site_values: dict[str, Any]
) -> SettingOut:
    """
    Merge a catalog definition with its resolved override values.

    Args:
        definition: The setting's catalog definition.
        brand_values: Brand-level overrides, keyed by setting_key.
        site_values: Site-level overrides, keyed by setting_key.

    Returns:
        SettingOut: The definition plus brand_value/site_value/effective_value.
    """
    brand_value = brand_values.get(definition.key)
    site_value = site_values.get(definition.key)
    if site_value is not None:
        effective = site_value
    elif brand_value is not None:
        effective = brand_value
    else:
        effective = definition.default_value
    return SettingOut(
        key=definition.key,
        label=definition.label,
        category=definition.category,
        type=definition.type,
        options=definition.options,
        default_value=definition.default_value,
        brand_value=brand_value,
        site_value=site_value,
        effective_value=effective,
    )


async def list_settings_for_scope(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID | None,
    search: str | None = None,
) -> list[SettingOut]:
    """
    Return the full setting catalog merged with brand/site override state.

    Backs the portal Settings management page — includes brand_value and
    site_value separately (not just the effective value) so the UI can show
    which level a setting is currently set at.

    Args:
        db: Active database session.
        brand_id: Brand to resolve brand-level defaults for.
        site_id: Optional site to also resolve site-level overrides for.
        search: Optional case-insensitive substring filter on key/label/category.

    Returns:
        list[SettingOut]: Matching settings, catalog order.
    """
    brand_values, site_values = await _load_overrides(db, brand_id, site_id)
    definitions = search_setting_definitions(search)
    return [_build_setting_out(d, brand_values, site_values) for d in definitions]


async def get_effective_settings_for_site(
    db: AsyncSession, site: Site, search: str | None = None
) -> list[SettingOut]:
    """
    Return the full setting catalog resolved for a single site.

    Backs the POS read endpoint — the Android app fetches this on launch
    (and searches it client-side for the Settings screen), consuming only
    effective_value from each row in practice.

    Args:
        db: Active database session.
        site: The site to resolve settings for.
        search: Optional case-insensitive substring filter.

    Returns:
        list[SettingOut]: Matching settings, catalog order.
    """
    return await list_settings_for_scope(db, site.brand_id, site.id, search)


async def _get_or_404_site_in_brand(db: AsyncSession, site_id: uuid.UUID, brand_id: uuid.UUID) -> Site:
    """
    Fetch a Site by ID, scoped to a brand, or raise HTTP 404/400.

    Args:
        db: Active database session.
        site_id: UUID of the site.
        brand_id: The brand the site must belong to.

    Returns:
        Site: The found site.

    Raises:
        HTTPException: 404 if the site doesn't exist; 400 if it belongs to a
            different brand than the caller's scope.
    """
    result = await db.execute(select(Site).where(Site.id == site_id))
    site = result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    if site.brand_id != brand_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site does not belong to this brand",
        )
    return site


async def upsert_setting(
    db: AsyncSession,
    key: str,
    value: Any,
    brand_id: uuid.UUID,
    site_id: uuid.UUID | None,
    actor: User,
) -> SettingOut:
    """
    Create or update a brand- or site-level setting override.

    Args:
        db: Active database session.
        key: The setting key — must exist in the catalog.
        value: The new value — validated against the catalog entry's type/options.
        brand_id: The brand this override belongs to.
        site_id: The site to override at, or None for the brand-level default.
        actor: The authenticated user making the change.

    Returns:
        SettingOut: The setting's full resolved state after the update.

    Raises:
        HTTPException: 404 if key is not a recognised setting or the site
            doesn't exist; 400 if the site belongs to a different brand;
            422 if the value fails type/option validation.
    """
    definition = get_setting_definition(key)
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown setting key")
    _validate_value(definition, value)

    if site_id is not None:
        await _get_or_404_site_in_brand(db, site_id, brand_id)

    existing_query = select(SettingValue).where(
        SettingValue.brand_id == brand_id, SettingValue.setting_key == key
    )
    existing_query = existing_query.where(
        SettingValue.site_id == site_id if site_id is not None else SettingValue.site_id.is_(None)
    )
    result = await db.execute(existing_query)
    row = result.scalar_one_or_none()

    before_state = {"value": row.value["value"]} if row is not None else None

    if row is None:
        row = SettingValue(
            id=uuid.uuid4(),
            brand_id=brand_id,
            site_id=site_id,
            setting_key=key,
            value={"value": value},
        )
        db.add(row)
    else:
        row.value = {"value": value}

    await log_action(
        db=db,
        action=SETTING_UPDATED,
        entity_type="setting_value",
        entity_id=key,
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before_state,
        after_state={
            "setting_key": key,
            "brand_id": str(brand_id),
            "site_id": str(site_id) if site_id else None,
            "value": value,
        },
    )
    await db.commit()

    brand_values, site_values = await _load_overrides(db, brand_id, site_id)
    log.info("setting.updated", setting_key=key, brand_id=str(brand_id), site_id=str(site_id) if site_id else None)
    return _build_setting_out(definition, brand_values, site_values)


async def clear_setting_override(
    db: AsyncSession,
    key: str,
    brand_id: uuid.UUID,
    site_id: uuid.UUID | None,
    actor: User,
) -> SettingOut:
    """
    Remove a brand- or site-level override, reverting to its fallback.

    Args:
        db: Active database session.
        key: The setting key to clear.
        brand_id: The brand scope.
        site_id: The site to clear the override for, or None for the brand-level default.
        actor: The authenticated user making the change.

    Returns:
        SettingOut: The setting's full resolved state after the reset.

    Raises:
        HTTPException: 404 if key is not a recognised setting, or no override exists.
    """
    definition = get_setting_definition(key)
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown setting key")

    query = select(SettingValue).where(
        SettingValue.brand_id == brand_id, SettingValue.setting_key == key
    )
    query = query.where(
        SettingValue.site_id == site_id if site_id is not None else SettingValue.site_id.is_(None)
    )
    result = await db.execute(query)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No override set for this scope")

    before_value = row.value["value"]
    await db.delete(row)

    await log_action(
        db=db,
        action=SETTING_RESET,
        entity_type="setting_value",
        entity_id=key,
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"value": before_value},
        after_state={
            "setting_key": key,
            "brand_id": str(brand_id),
            "site_id": str(site_id) if site_id else None,
        },
    )
    await db.commit()

    brand_values, site_values = await _load_overrides(db, brand_id, site_id)
    log.info("setting.reset", setting_key=key, brand_id=str(brand_id), site_id=str(site_id) if site_id else None)
    return _build_setting_out(definition, brand_values, site_values)
