"""Unit tests for tax_id_label_for_country.

Covers:
1. Mapped countries return their specific label
2. Unmapped countries fall back to DEFAULT_TAX_ID_LABEL
3. Lookup is case-insensitive and trims whitespace
"""

from app.constants.tax_id_labels import DEFAULT_TAX_ID_LABEL, tax_id_label_for_country


def test_mapped_country_returns_specific_label():
    """AU maps to 'ABN', not the default label."""
    assert tax_id_label_for_country("AU") == "ABN"


def test_other_mapped_countries_return_specific_labels():
    """A sample of other mapped countries resolve to their own labels."""
    assert tax_id_label_for_country("NZ") == "NZBN"
    assert tax_id_label_for_country("GB") == "VAT Number"
    assert tax_id_label_for_country("US") == "EIN"


def test_unmapped_country_falls_back_to_default():
    """A country with no specific mapping returns DEFAULT_TAX_ID_LABEL."""
    assert tax_id_label_for_country("ZZ") == DEFAULT_TAX_ID_LABEL


def test_lookup_is_case_insensitive():
    """Lowercase country codes resolve the same as uppercase."""
    assert tax_id_label_for_country("au") == "ABN"


def test_lookup_trims_whitespace():
    """Surrounding whitespace does not break the lookup."""
    assert tax_id_label_for_country(" AU ") == "ABN"
