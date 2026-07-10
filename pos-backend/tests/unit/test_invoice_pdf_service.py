"""Unit tests for invoice PDF HTML generation (Stage 21) — no database, no rendering."""

import uuid
from datetime import datetime, timezone

from app.services.invoice_pdf_service import build_invoice_html
from app.services.invoice_report_service import (
    InvoiceDetailLineItem,
    InvoiceDetailModifier,
    InvoiceDetailResponse,
    InvoiceDetailTaxRow,
    PaymentResponse,
)


def _make_invoice(**overrides) -> InvoiceDetailResponse:
    """Build a minimal InvoiceDetailResponse for HTML-generation tests."""
    defaults = dict(
        id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        site_id=uuid.uuid4(),
        site_name="Main Street",
        brand_name="Burger Co",
        created_by_id=None,
        invoice_type="sale",
        status="paid",
        subtotal_cents=1000,
        tax_cents=91,
        discount_cents=0,
        discount_reason=None,
        total_cents=1000,
        refund_of_id=None,
        is_refunded=False,
        voided_at=None,
        paid_at=datetime.now(tz=timezone.utc),
        created_at=datetime.now(tz=timezone.utc),
        line_items=[],
        tax_breakdown=[],
        payments=[],
    )
    defaults.update(overrides)
    return InvoiceDetailResponse(**defaults)


def test_build_invoice_html_includes_brand_and_site_names():
    """The rendered HTML includes the invoice's brand and site names."""
    invoice = _make_invoice()
    html_doc = build_invoice_html(invoice)
    assert "Burger Co" in html_doc
    assert "Main Street" in html_doc


def test_build_invoice_html_escapes_product_name():
    """A product name containing HTML-special characters is escaped, not injected raw."""
    invoice = _make_invoice(
        line_items=[
            InvoiceDetailLineItem(
                id=uuid.uuid4(),
                product_id=uuid.uuid4(),
                product_name="<script>alert(1)</script>",
                unit_price_cents=1000,
                quantity=1,
                subtotal_cents=1000,
                tax_cents=91,
                line_total_cents=1000,
                display_order=0,
                modifiers=[],
            )
        ]
    )
    html_doc = build_invoice_html(invoice)
    assert "<script>alert(1)</script>" not in html_doc
    assert "&lt;script&gt;" in html_doc


def test_build_invoice_html_renders_modifiers_tax_and_payments():
    """Modifiers, tax breakdown rows, and payments all appear in the output."""
    line_item_id = uuid.uuid4()
    invoice = _make_invoice(
        line_items=[
            InvoiceDetailLineItem(
                id=line_item_id,
                product_id=uuid.uuid4(),
                product_name="Cheeseburger",
                unit_price_cents=1000,
                quantity=1,
                subtotal_cents=1000,
                tax_cents=91,
                line_total_cents=1000,
                display_order=0,
                modifiers=[
                    InvoiceDetailModifier(id=uuid.uuid4(), modifier_name="Extra Cheese", price_delta_cents=150)
                ],
            )
        ],
        tax_breakdown=[
            InvoiceDetailTaxRow(
                id=uuid.uuid4(),
                tax_rate_name="GST",
                rate_percent="10.0000",
                tax_model="inclusive",
                taxable_amount_cents=909,
                tax_amount_cents=91,
            )
        ],
        payments=[
            PaymentResponse(
                id=uuid.uuid4(),
                invoice_id=uuid.uuid4(),
                method="cash",
                amount_cents=1000,
                reference=None,
                paid_at=datetime.now(tz=timezone.utc),
            )
        ],
    )
    html_doc = build_invoice_html(invoice)
    assert "Cheeseburger" in html_doc
    assert "Extra Cheese" in html_doc
    assert "GST" in html_doc
    assert "Cash" in html_doc


def test_build_invoice_html_shows_discount_reason_when_present():
    """A discount with a reason renders the reason alongside the discount line."""
    invoice = _make_invoice(discount_cents=200, discount_reason="Loyalty discount", total_cents=800)
    html_doc = build_invoice_html(invoice)
    assert "Loyalty discount" in html_doc
    assert "-$2.00" in html_doc
