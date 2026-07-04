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
from decimal import ROUND_HALF_UP, Decimal

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
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


async def country_inclusive_rate(db: AsyncSession, country: str) -> Decimal:
    """
    Return the combined inclusive tax percentage for a country's national templates.

    Sums the active inclusive rates of every country-level template (no
    state/county/city set) for the country — for AU that is a single 10% GST.
    Used to split a product's tax-inclusive price into its exclusive component
    at product-save time.

    Args:
        db: Active database session.
        country: ISO 3166-1 alpha-2 country code.

    Returns:
        Decimal: The combined inclusive rate percentage (0 when none exists).
    """
    result = await db.execute(
        select(func.coalesce(func.sum(TaxTemplateRate.rate_percent), 0))
        .select_from(TaxTemplate)
        .join(TaxTemplateRate, TaxTemplateRate.tax_template_id == TaxTemplate.id)
        .where(
            TaxTemplate.is_active == True,  # noqa: E712
            func.lower(TaxTemplate.country) == country.strip().lower(),
            TaxTemplate.state.is_(None),
            TaxTemplate.county.is_(None),
            TaxTemplate.city.is_(None),
            TaxTemplateRate.is_active == True,  # noqa: E712
            TaxTemplateRate.tax_model == "inclusive",
        )
    )
    return Decimal(str(result.scalar_one()))


async def derive_ex_price_cents(db: AsyncSession, brand_id: uuid.UUID, inc_cents: int) -> int:
    """
    Derive the tax-exclusive price from a tax-inclusive price for a brand.

    Uses the brand's country combined inclusive rate: ex = inc × 100 / (100 + rate),
    rounded to the nearest cent. When the brand's country has no inclusive
    template the rate is 0 and the exclusive price equals the inclusive price.

    Args:
        db: Active database session.
        brand_id: Brand the product belongs to.
        inc_cents: The tax-inclusive price in cents.

    Returns:
        int: The tax-exclusive price in cents.
    """
    brand_result = await db.execute(select(Brand.country).where(Brand.id == brand_id))
    country = brand_result.scalar_one_or_none()
    if country is None:
        return inc_cents

    rate = await country_inclusive_rate(db, country)
    if rate == 0:
        return inc_cents

    ex = Decimal(inc_cents) * Decimal("100") / (Decimal("100") + rate)
    return int(ex.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


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
