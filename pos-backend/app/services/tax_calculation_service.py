"""Tax calculation service for the invoice engine.

Computes per-line-item tax amounts given a unit price, quantity, and a list
of active TaxRate specs.

Tax models (from TaxModel enum in constants/statuses.py):
  - exclusive: tax is added ON TOP of the displayed price.
               tax = subtotal × rate / 100
  - inclusive: tax is EMBEDDED in the displayed price.
               tax = subtotal × rate / (100 + rate)
               The line total does NOT increase — tax is extracted from the price.
  - compound:  multiple rates, EACH applied independently to the base price.
               Same formula as exclusive: tax_i = subtotal × rate_i / 100.
               The distinction from exclusive is a reporting label only — it
               signals "applied in parallel to a base price, not stacked".

All arithmetic uses Python Decimal to avoid floating-point errors (rule 9).
Final cent values are rounded to the nearest integer using ROUND_HALF_UP.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


@dataclass
class TaxLineResult:
    """
    Result of calculate_line_tax() for one line item.

    Attributes:
        subtotal_cents: unit_price_cents × quantity.
        tax_cents: total tax collected across all rates.
        line_total_cents: amount charged to customer (subtotal + exclusive tax).
        rate_breakdowns: per-rate taxable_amount_cents and tax_amount_cents,
            used to build InvoiceTaxBreakdown rows.
    """

    subtotal_cents: int
    tax_cents: int
    line_total_cents: int
    rate_breakdowns: list[dict[str, Any]] = field(default_factory=list)


def calculate_line_tax(
    unit_price_cents: int,
    quantity: int,
    rates: list[dict[str, Any]],
) -> TaxLineResult:
    """
    Calculate tax for a single invoice line item.

    Args:
        unit_price_cents: Effective unit price in cents (snapshot value).
        quantity: Number of units.
        rates: List of rate spec dicts — each must contain:
            - rate_id: str UUID of the TaxRate
            - rate_name: str label for the receipt
            - rate_percent: Decimal percentage (e.g. Decimal("10.0000"))
            - tax_model: str — "exclusive", "inclusive", or "compound"

    Returns:
        TaxLineResult: Computed subtotal, tax, line_total, and per-rate breakdowns.
    """
    subtotal = unit_price_cents * quantity  # integer — no Decimal needed yet

    total_tax = 0
    extra_on_top = 0  # additional exclusive/compound tax added to total
    breakdowns: list[dict[str, Any]] = []

    for rate in rates:
        rate_pct: Decimal = rate["rate_percent"]
        model: str = rate["tax_model"]

        if model in ("exclusive", "compound"):
            # Tax is calculated on top of the subtotal
            tax_dec = Decimal(subtotal) * rate_pct / Decimal("100")
            tax_cents = int(tax_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            extra_on_top += tax_cents
        elif model == "inclusive":
            # Tax is already embedded in the price; extract it
            # tax = subtotal × rate / (100 + rate)
            denominator = Decimal("100") + rate_pct
            tax_dec = Decimal(subtotal) * rate_pct / denominator
            tax_cents = int(tax_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            # Inclusive tax does NOT increase the line total
        else:
            tax_cents = 0

        total_tax += tax_cents
        breakdowns.append(
            {
                "rate_id": rate["rate_id"],
                "rate_name": rate["rate_name"],
                "rate_percent": rate_pct,
                "tax_model": model,
                "taxable_amount_cents": subtotal,
                "tax_amount_cents": tax_cents,
            }
        )

    return TaxLineResult(
        subtotal_cents=subtotal,
        tax_cents=total_tax,
        line_total_cents=subtotal + extra_on_top,
        rate_breakdowns=breakdowns,
    )
