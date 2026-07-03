"""Business logic for admin-managed tax templates and their rates.

Templates are SuperAdmin-portal-only: management (customer) users never see
or modify them. Every write logs an audit row in the same transaction.
"""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    TAX_TEMPLATE_CREATED,
    TAX_TEMPLATE_DELETED,
    TAX_TEMPLATE_RATE_CREATED,
    TAX_TEMPLATE_RATE_DELETED,
    TAX_TEMPLATE_RATE_UPDATED,
    TAX_TEMPLATE_UPDATED,
)
from app.constants.statuses import ActorType
from app.models.superadmin import SuperAdmin
from app.models.tax_template import TaxTemplate
from app.models.tax_template_rate import TaxTemplateRate
from app.schemas.tax_template import (
    TaxTemplateCreate,
    TaxTemplateRateCreate,
    TaxTemplateRateResponse,
    TaxTemplateRateUpdate,
    TaxTemplateResponse,
    TaxTemplateUpdate,
)
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


def _template_state(template: TaxTemplate) -> dict:
    """Snapshot a template's jurisdiction fields for audit before/after states."""
    return {
        "name": template.name,
        "country": template.country,
        "state": template.state,
        "county": template.county,
        "city": template.city,
        "is_active": template.is_active,
    }


def _rate_state(rate: TaxTemplateRate) -> dict:
    """Snapshot a rate's fields for audit before/after states."""
    return {
        "name": rate.name,
        "rate_percent": str(rate.rate_percent),
        "tax_model": rate.tax_model,
        "display_order": rate.display_order,
        "is_active": rate.is_active,
    }


async def _get_template_or_404(db: AsyncSession, template_id: uuid.UUID) -> TaxTemplate:
    """Fetch an active-or-inactive template by ID or raise HTTP 404."""
    result = await db.execute(select(TaxTemplate).where(TaxTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tax template not found")
    return template


async def _get_rate_or_404(db: AsyncSession, rate_id: uuid.UUID) -> TaxTemplateRate:
    """Fetch a template rate by ID or raise HTTP 404."""
    result = await db.execute(select(TaxTemplateRate).where(TaxTemplateRate.id == rate_id))
    rate = result.scalar_one_or_none()
    if rate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tax template rate not found")
    return rate


async def _to_response(db: AsyncSession, template: TaxTemplate) -> TaxTemplateResponse:
    """Build a TaxTemplateResponse with the template's active rates attached."""
    rates_result = await db.execute(
        select(TaxTemplateRate)
        .where(
            TaxTemplateRate.tax_template_id == template.id,
            TaxTemplateRate.is_active == True,  # noqa: E712
        )
        .order_by(TaxTemplateRate.display_order, TaxTemplateRate.created_at)
    )
    rates = [TaxTemplateRateResponse.model_validate(r) for r in rates_result.scalars().all()]
    response = TaxTemplateResponse.model_validate(template)
    response.rates = rates
    return response


async def list_templates(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    country: str | None = None,
) -> list[TaxTemplateResponse]:
    """
    Return a paginated list of tax templates with their rates.

    Args:
        db: Active database session.
        skip: Number of records to skip (offset).
        limit: Maximum number of records to return.
        country: Optional exact-match filter on the ISO country code.

    Returns:
        list[TaxTemplateResponse]: Templates ordered by country then jurisdiction depth.
    """
    conditions = []
    if country is not None:
        conditions.append(TaxTemplate.country == country.upper())

    result = await db.execute(
        select(TaxTemplate)
        .where(*conditions)
        .order_by(TaxTemplate.country, TaxTemplate.state, TaxTemplate.county, TaxTemplate.city)
        .offset(skip)
        .limit(limit)
    )
    templates = list(result.scalars().all())
    return [await _to_response(db, t) for t in templates]


async def create_template(
    db: AsyncSession,
    payload: TaxTemplateCreate,
    actor: SuperAdmin,
) -> TaxTemplateResponse:
    """
    Create a tax template and write an audit log row.

    Args:
        db: Active database session.
        payload: Template jurisdiction fields.
        actor: The authenticated admin performing the action.

    Returns:
        TaxTemplateResponse: The created template (no rates yet).
    """
    template = TaxTemplate(
        id=uuid.uuid4(),
        name=payload.name,
        country=payload.country.upper(),
        state=payload.state,
        county=payload.county,
        city=payload.city,
        is_active=True,
    )
    db.add(template)
    await db.flush()

    await log_action(
        db=db,
        action=TAX_TEMPLATE_CREATED,
        entity_type="tax_template",
        entity_id=str(template.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state=_template_state(template),
    )
    await db.commit()
    log.info("tax_template.created", template_id=str(template.id), country=template.country)
    return await _to_response(db, template)


async def update_template(
    db: AsyncSession,
    template_id: uuid.UUID,
    payload: TaxTemplateUpdate,
    actor: SuperAdmin,
) -> TaxTemplateResponse:
    """
    Update a tax template's fields and write an audit log row.

    Args:
        db: Active database session.
        template_id: UUID of the template to update.
        payload: Fields to change (all optional).
        actor: The authenticated admin performing the action.

    Returns:
        TaxTemplateResponse: The updated template with its rates.

    Raises:
        HTTPException: 404 if the template does not exist.
    """
    template = await _get_template_or_404(db, template_id)
    before = _template_state(template)

    if payload.name is not None:
        template.name = payload.name
    if payload.country is not None:
        template.country = payload.country.upper()
    if payload.state is not None:
        # Empty string clears the field back to jurisdiction-wide
        template.state = payload.state or None
    if payload.county is not None:
        template.county = payload.county or None
    if payload.city is not None:
        template.city = payload.city or None
    if payload.is_active is not None:
        template.is_active = payload.is_active

    await log_action(
        db=db,
        action=TAX_TEMPLATE_UPDATED,
        entity_type="tax_template",
        entity_id=str(template.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=_template_state(template),
    )
    await db.commit()
    await db.refresh(template)
    return await _to_response(db, template)


async def delete_template(
    db: AsyncSession,
    template_id: uuid.UUID,
    actor: SuperAdmin,
) -> None:
    """
    Soft-delete a tax template (is_active = False) and write an audit log row.

    Inactive templates never match any site, so their rates stop applying
    immediately; historical invoices are unaffected (rates are snapshotted).

    Args:
        db: Active database session.
        template_id: UUID of the template to deactivate.
        actor: The authenticated admin performing the action.

    Raises:
        HTTPException: 404 if the template does not exist.
        HTTPException: 409 if the template is already inactive.
    """
    template = await _get_template_or_404(db, template_id)
    if not template.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Tax template is already inactive"
        )

    template.is_active = False

    await log_action(
        db=db,
        action=TAX_TEMPLATE_DELETED,
        entity_type="tax_template",
        entity_id=str(template.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": True},
        after_state={"is_active": False},
    )
    await db.commit()
    log.info("tax_template.deleted", template_id=str(template.id))


async def create_rate(
    db: AsyncSession,
    template_id: uuid.UUID,
    payload: TaxTemplateRateCreate,
    actor: SuperAdmin,
) -> TaxTemplateRateResponse:
    """
    Add a rate to a tax template and write an audit log row.

    Args:
        db: Active database session.
        template_id: Parent template UUID.
        payload: Rate fields.
        actor: The authenticated admin performing the action.

    Returns:
        TaxTemplateRateResponse: The created rate.

    Raises:
        HTTPException: 404 if the template does not exist.
    """
    template = await _get_template_or_404(db, template_id)

    rate = TaxTemplateRate(
        id=uuid.uuid4(),
        tax_template_id=template.id,
        name=payload.name,
        rate_percent=payload.rate_percent,
        tax_model=payload.tax_model.value,
        display_order=payload.display_order,
        is_active=True,
    )
    db.add(rate)
    await db.flush()

    await log_action(
        db=db,
        action=TAX_TEMPLATE_RATE_CREATED,
        entity_type="tax_template_rate",
        entity_id=str(rate.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state=_rate_state(rate),
    )
    await db.commit()
    await db.refresh(rate)
    log.info("tax_template_rate.created", rate_id=str(rate.id), template_id=str(template.id))
    return TaxTemplateRateResponse.model_validate(rate)


async def update_rate(
    db: AsyncSession,
    rate_id: uuid.UUID,
    payload: TaxTemplateRateUpdate,
    actor: SuperAdmin,
) -> TaxTemplateRateResponse:
    """
    Update a template rate's fields and write an audit log row.

    Args:
        db: Active database session.
        rate_id: UUID of the rate to update.
        payload: Fields to change (all optional).
        actor: The authenticated admin performing the action.

    Returns:
        TaxTemplateRateResponse: The updated rate.

    Raises:
        HTTPException: 404 if the rate does not exist.
    """
    rate = await _get_rate_or_404(db, rate_id)
    before = _rate_state(rate)

    if payload.name is not None:
        rate.name = payload.name
    if payload.rate_percent is not None:
        rate.rate_percent = payload.rate_percent
    if payload.tax_model is not None:
        rate.tax_model = payload.tax_model.value
    if payload.display_order is not None:
        rate.display_order = payload.display_order

    await log_action(
        db=db,
        action=TAX_TEMPLATE_RATE_UPDATED,
        entity_type="tax_template_rate",
        entity_id=str(rate.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=_rate_state(rate),
    )
    await db.commit()
    await db.refresh(rate)
    return TaxTemplateRateResponse.model_validate(rate)


async def delete_rate(
    db: AsyncSession,
    rate_id: uuid.UUID,
    actor: SuperAdmin,
) -> None:
    """
    Soft-delete a template rate (is_active = False) and write an audit log row.

    Args:
        db: Active database session.
        rate_id: UUID of the rate to deactivate.
        actor: The authenticated admin performing the action.

    Raises:
        HTTPException: 404 if the rate does not exist.
        HTTPException: 409 if the rate is already inactive.
    """
    rate = await _get_rate_or_404(db, rate_id)
    if not rate.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Tax template rate is already inactive"
        )

    rate.is_active = False

    await log_action(
        db=db,
        action=TAX_TEMPLATE_RATE_DELETED,
        entity_type="tax_template_rate",
        entity_id=str(rate.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": True},
        after_state={"is_active": False},
    )
    await db.commit()
    log.info("tax_template_rate.deleted", rate_id=str(rate.id))
