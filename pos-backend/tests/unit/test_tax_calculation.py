"""Unit tests for tax_calculation_service.

Three scenarios covering all three TaxModel values.
All monetary assertions compare integer cents — no floats (rule 9).
"""

from decimal import Decimal

import pytest

from app.services.tax_calculation_service import TaxLineResult, calculate_line_tax


def _rate(rate_percent: str, tax_model: str) -> dict:
    """Helper to build a rate spec dict for calculate_line_tax."""
    return {
        "rate_id": "00000000-0000-0000-0000-000000000001",
        "rate_name": "Test Tax",
        "rate_percent": Decimal(rate_percent),
        "tax_model": tax_model,
    }


def test_exclusive_tax_adds_on_top_of_price() -> None:
    """Exclusive tax is calculated as subtotal × rate / 100 and added to the total."""
    result = calculate_line_tax(
        unit_price_cents=1000,
        quantity=2,
        rates=[_rate("10.0000", "exclusive")],
    )
    # subtotal = 1000 × 2 = 2000
    # tax = 2000 × 10/100 = 200
    # line_total = 2000 + 200 = 2200
    assert result.subtotal_cents == 2000
    assert result.tax_cents == 200
    assert result.line_total_cents == 2200
    assert len(result.rate_breakdowns) == 1
    assert result.rate_breakdowns[0]["tax_amount_cents"] == 200
    assert result.rate_breakdowns[0]["taxable_amount_cents"] == 2000


def test_inclusive_tax_extracts_tax_from_price() -> None:
    """Inclusive tax is extracted from the price — the total does not increase."""
    result = calculate_line_tax(
        unit_price_cents=1100,
        quantity=1,
        rates=[_rate("10.0000", "inclusive")],
    )
    # unit_price already includes 10% GST
    # tax = 1100 × 10 / (100 + 10) = 1100 × 10/110 = 100
    # subtotal = 1100 (inclusive price, no extra added)
    # line_total = 1100 (same as subtotal — tax is already in the price)
    assert result.subtotal_cents == 1100
    assert result.tax_cents == 100
    assert result.line_total_cents == 1100  # no additional amount added


def test_compound_tax_applies_both_rates_to_base() -> None:
    """Compound tax: each rate is applied independently to the base price (not stacked)."""
    result = calculate_line_tax(
        unit_price_cents=1000,
        quantity=1,
        rates=[
            _rate("5.0000", "compound"),   # PST: 1000 × 5/100 = 50
            _rate("10.0000", "exclusive"),  # GST: 1000 × 10/100 = 100
        ],
    )
    # Both rates are applied to the base 1000
    # compound PST = 50, exclusive GST = 100
    # total tax = 150
    # line_total = 1000 + 150 = 1150
    assert result.subtotal_cents == 1000
    assert result.tax_cents == 150
    assert result.line_total_cents == 1150


def test_zero_tax_rate_returns_zero_tax() -> None:
    """A 0% rate produces zero tax and the total equals the subtotal."""
    result = calculate_line_tax(
        unit_price_cents=500,
        quantity=3,
        rates=[_rate("0.0000", "exclusive")],
    )
    assert result.subtotal_cents == 1500
    assert result.tax_cents == 0
    assert result.line_total_cents == 1500


def test_no_rates_returns_zero_tax() -> None:
    """When no tax rates are provided the line total equals the subtotal."""
    result = calculate_line_tax(
        unit_price_cents=800,
        quantity=2,
        rates=[],
    )
    assert result.subtotal_cents == 1600
    assert result.tax_cents == 0
    assert result.line_total_cents == 1600
    assert result.rate_breakdowns == []
