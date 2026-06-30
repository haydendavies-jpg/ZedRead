"""Read-only reference data routes backing the company-profile dropdowns
(timezone/currency/country selects and the country-driven tax ID label)
shared by the SuperAdmin portal and the tenant-facing management portal."""

from fastapi import APIRouter, Depends, Query

from app.constants.countries import CodeName, list_countries, list_currencies
from app.constants.tax_id_labels import tax_id_label_for_country
from app.constants.timezones import list_timezones
from app.schemas.reference_data import TaxIdLabelResponse
from app.utils.dependencies import resolve_catalog_access

router = APIRouter(prefix="/reference", tags=["reference-data"])


@router.get("/timezones", response_model=list[str])
async def get_timezones(
    access=Depends(resolve_catalog_access),
) -> list[str]:
    """Return all known IANA timezone names, sorted alphabetically."""
    return list_timezones()


@router.get("/countries", response_model=list[CodeName])
async def get_countries(
    access=Depends(resolve_catalog_access),
) -> list[CodeName]:
    """Return all ISO 3166-1 countries, sorted by name."""
    return list_countries()


@router.get("/currencies", response_model=list[CodeName])
async def get_currencies(
    access=Depends(resolve_catalog_access),
) -> list[CodeName]:
    """Return all ISO 4217 currencies, sorted by name."""
    return list_currencies()


@router.get("/tax-id-label", response_model=TaxIdLabelResponse)
async def get_tax_id_label(
    country: str = Query(..., min_length=2, max_length=2, description="ISO 3166-1 alpha-2 country code"),
    access=Depends(resolve_catalog_access),
) -> TaxIdLabelResponse:
    """Return the tax ID field label for a given country code."""
    return TaxIdLabelResponse(label=tax_id_label_for_country(country))
