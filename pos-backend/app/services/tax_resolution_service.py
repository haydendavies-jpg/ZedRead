"""Resolve which admin-managed tax rates apply to a site at sale time.

Tax templates are jurisdiction-scoped (country → state → county → city).
A template applies to a site when EVERY jurisdiction field the template has
set matches the site's location; unset template fields are ignored. All
matching templates' active rates combine (additively by default — a rate's
tax_model marks it inclusive/exclusive/compound for the calculation engine).

Example: an AU site matches the country=AU template only (10% GST). A future
Texan site would match country=US, plus country=US/state=TX, plus its county
row, and the rates sum — the foundation for regional tax markets.
"""

import uuid

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.site import Site
from app.models.tax_template import TaxTemplate
from app.models.tax_template_rate import TaxTemplateRate

log = structlog.get_logger(__name__)


def _normalise(value: str | None) -> str | None:
    """Lower-case and trim a location field; empty strings become None."""
    if value is None:
        return None
    trimmed = value.strip().lower()
    return trimmed or None


async def resolve_rates_for_location(
    db: AsyncSession,
    country: str,
    state: str | None = None,
    county: str | None = None,
    city: str | None = None,
) -> list[dict]:
    """
    Return the combined rate specs for a location from all matching templates.

    A template matches when each of its set jurisdiction fields equals the
    corresponding location field (case-insensitive); templates with a field
    set that the location lacks do not match.

    Args:
        db: Active database session.
        country: ISO 3166-1 alpha-2 country code (required).
        state: State/province of the location, if known.
        county: County/region of the location, if known.
        city: City/suburb of the location, if known.

    Returns:
        list[dict]: Rate spec dicts (rate_id, rate_name, rate_percent,
            tax_model) in template display order, ready for calculate_line_tax().
    """
    norm_state = _normalise(state)
    norm_county = _normalise(county)
    norm_city = _normalise(city)

    # A template field matches when it is NULL (not constrained) or equals the
    # location value; a set template field with no location value never matches.
    def _field_condition(column, value: str | None):
        """Build the NULL-or-equal condition for one jurisdiction column."""
        if value is None:
            return column.is_(None)
        return or_(column.is_(None), func.lower(func.trim(column)) == value)

    result = await db.execute(
        select(TaxTemplate).where(
            TaxTemplate.is_active == True,  # noqa: E712
            func.lower(TaxTemplate.country) == country.strip().lower(),
            _field_condition(TaxTemplate.state, norm_state),
            _field_condition(TaxTemplate.county, norm_county),
            _field_condition(TaxTemplate.city, norm_city),
        )
    )
    templates = list(result.scalars().all())
    if not templates:
        log.info("tax.resolution.no_templates", country=country)
        return []

    rates_result = await db.execute(
        select(TaxTemplateRate)
        .where(
            TaxTemplateRate.tax_template_id.in_([t.id for t in templates]),
            TaxTemplateRate.is_active == True,  # noqa: E712
        )
        .order_by(TaxTemplateRate.display_order, TaxTemplateRate.created_at)
    )
    rates = rates_result.scalars().all()

    return [
        {
            "rate_id": str(r.id),
            "rate_name": r.name,
            "rate_percent": r.rate_percent,
            "tax_model": r.tax_model,
        }
        for r in rates
    ]


async def resolve_rates_for_site(db: AsyncSession, site_id: uuid.UUID) -> list[dict]:
    """
    Resolve the applicable tax rate specs for a site by its location.

    Uses the site's country and address_state/address_city. Sites do not
    currently record a county, so county-level templates never match — the
    schema supports them for future regional markets.

    Args:
        db: Active database session.
        site_id: UUID of the site the sale is happening at.

    Returns:
        list[dict]: Rate specs for calculate_line_tax(); empty if the site
            is unknown or no template matches its location.
    """
    result = await db.execute(select(Site).where(Site.id == site_id))
    site = result.scalar_one_or_none()
    if site is None:
        # Unknown site — no rates rather than an exception; the invoice
        # routes have already validated site scope before reaching here.
        log.info("tax.resolution.site_not_found", site_id=str(site_id))
        return []

    return await resolve_rates_for_location(
        db,
        country=site.country,
        state=site.address_state,
        county=None,
        city=site.address_city,
    )
