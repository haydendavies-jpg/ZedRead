"""Country-specific labels for the free-text tax ID field on Group/Brand/Site
company profiles (e.g. 'ABN' in Australia, 'EIN' in the US).

Same shape as license_plans.allowed_pages_for_plan(): a plain dict, a
lookup function, and a sane fallback for any country not yet mapped — easy
to extend without a migration.
"""

DEFAULT_TAX_ID_LABEL = "Tax ID"

TAX_ID_LABEL_BY_COUNTRY: dict[str, str] = {
    "AU": "ABN",
    "NZ": "NZBN",
    "GB": "VAT Number",
    "US": "EIN",
    "CA": "Business Number",
    "IE": "VAT Number",
    "SG": "UEN",
}


def tax_id_label_for_country(country_code: str) -> str:
    """
    Return the tax ID field label for a given ISO 3166-1 alpha-2 country code.

    Args:
        country_code: ISO 3166-1 alpha-2 country code (case-insensitive).

    Returns:
        str: The country-specific label, or DEFAULT_TAX_ID_LABEL if the
        country has no specific mapping.
    """
    return TAX_ID_LABEL_BY_COUNTRY.get(country_code.strip().upper(), DEFAULT_TAX_ID_LABEL)
