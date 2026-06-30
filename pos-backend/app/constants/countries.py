"""ISO 3166-1 country and ISO 4217 currency reference data, used to
populate the country/currency dropdowns on Group/Brand/Site create and
edit forms."""

from pydantic import BaseModel

import pycountry


class CodeName(BaseModel):
    """A single reference-data option: a code and its display name."""

    code: str
    name: str


def list_countries() -> list[CodeName]:
    """
    Return all ISO 3166-1 alpha-2 countries, sorted by name.

    Returns:
        list[CodeName]: e.g. [CodeName(code="AU", name="Australia"), ...].
    """
    countries = [CodeName(code=c.alpha_2, name=c.name) for c in pycountry.countries]
    return sorted(countries, key=lambda c: c.name)


def list_currencies() -> list[CodeName]:
    """
    Return all ISO 4217 currency codes, sorted by name.

    Returns:
        list[CodeName]: e.g. [CodeName(code="AUD", name="Australian Dollar"), ...].
    """
    currencies = [CodeName(code=c.alpha_3, name=c.name) for c in pycountry.currencies]
    return sorted(currencies, key=lambda c: c.name)
