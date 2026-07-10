"""PDF export for a single invoice (Stage 21).

No existing PDF style to match and no user preference given, so this renders
a plain, standard single-invoice layout authored as HTML/CSS and converted
with weasyprint — easiest to iterate on and restyle later, per the Stage 21
plan's recommendation over a programmatic library like reportlab.
"""

import html

from weasyprint import HTML

from app.services.invoice_report_service import InvoiceDetailResponse


def _cents_to_display(cents: int) -> str:
    """Format a cents integer as a signed dollar string, e.g. -150 -> '-$1.50'."""
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:.2f}"


def _esc(value: str | None) -> str:
    """HTML-escape a value for safe interpolation into the template, treating None as empty."""
    return html.escape(value or "")


def _line_item_rows(invoice: InvoiceDetailResponse) -> str:
    """Build the <tr> rows for the line items table, including nested modifier rows."""
    if not invoice.line_items:
        return '<tr><td colspan="4">No line items.</td></tr>'

    rows: list[str] = []
    for item in invoice.line_items:
        rows.append(
            f"<tr><td>{_esc(item.product_name)}</td>"
            f'<td class="num">{item.quantity}</td>'
            f'<td class="num">{_cents_to_display(item.unit_price_cents)}</td>'
            f'<td class="num">{_cents_to_display(item.line_total_cents)}</td></tr>'
        )
        for modifier in item.modifiers:
            rows.append(
                f'<tr class="modifier-row"><td>&nbsp;&nbsp;+ {_esc(modifier.modifier_name)}</td>'
                f'<td></td><td></td>'
                f'<td class="num">{_cents_to_display(modifier.price_delta_cents)}</td></tr>'
            )
    return "".join(rows)


def _tax_breakdown_table(invoice: InvoiceDetailResponse) -> str:
    """Build the tax breakdown table, or an empty string if there's nothing to tax."""
    if not invoice.tax_breakdown:
        return ""
    rows = "".join(
        f"<tr><td>{_esc(t.tax_rate_name)} ({t.rate_percent}%)</td>"
        f'<td class="num">{_cents_to_display(t.taxable_amount_cents)}</td>'
        f'<td class="num">{_cents_to_display(t.tax_amount_cents)}</td></tr>'
        for t in invoice.tax_breakdown
    )
    return (
        '<table><thead><tr><th>Tax</th><th class="num">Taxable</th>'
        f'<th class="num">Tax</th></tr></thead><tbody>{rows}</tbody></table>'
    )


def _payments_table(invoice: InvoiceDetailResponse) -> str:
    """Build the payments table, or an empty string if the invoice has no payments yet."""
    if not invoice.payments:
        return ""
    rows = "".join(
        f"<tr><td>{_esc(p.method.title())}</td><td>{_esc(p.reference)}</td>"
        f'<td class="num">{_cents_to_display(p.amount_cents)}</td></tr>'
        for p in invoice.payments
    )
    return (
        '<table><thead><tr><th>Payment</th><th>Reference</th>'
        f'<th class="num">Amount</th></tr></thead><tbody>{rows}</tbody></table>'
    )


def _totals_rows(invoice: InvoiceDetailResponse) -> str:
    """Build the summary totals rows: subtotal, tax, optional discount, grand total."""
    rows = [
        f'<tr><td>Subtotal</td><td class="num">{_cents_to_display(invoice.subtotal_cents)}</td></tr>',
        f'<tr><td>Tax</td><td class="num">{_cents_to_display(invoice.tax_cents)}</td></tr>',
    ]
    if invoice.discount_cents:
        reason = f" ({_esc(invoice.discount_reason)})" if invoice.discount_reason else ""
        rows.append(
            f"<tr><td>Discount{reason}</td>"
            f'<td class="num">-{_cents_to_display(invoice.discount_cents)}</td></tr>'
        )
    rows.append(
        f'<tr class="grand"><td>Total</td><td class="num">{_cents_to_display(invoice.total_cents)}</td></tr>'
    )
    return "".join(rows)


_STYLE = """
body { font-family: 'Helvetica Neue', Arial, sans-serif; color: #1f2937; font-size: 11pt; }
h1 { font-size: 18pt; margin-bottom: 0; }
.subtitle { color: #6b7280; font-size: 9pt; margin-top: 2px; }
.meta { margin-top: 16px; display: flex; justify-content: space-between; }
.meta div { font-size: 10pt; }
table { width: 100%; border-collapse: collapse; margin-top: 16px; }
th { text-align: left; border-bottom: 1px solid #1f2937; padding: 6px 4px; font-size: 9pt;
     text-transform: uppercase; color: #6b7280; }
td { padding: 6px 4px; border-bottom: 1px solid #e5e7eb; font-size: 10pt; }
td.num, th.num { text-align: right; }
.modifier-row td { color: #6b7280; font-size: 9pt; border-bottom: none; }
.totals { margin-top: 12px; width: 260px; margin-left: auto; }
.totals td { border-bottom: none; padding: 2px 4px; }
.totals .grand td { font-weight: bold; border-top: 1px solid #1f2937; padding-top: 6px; }
.status { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 9pt;
          text-transform: uppercase; background: #f3f4f6; }
"""


def build_invoice_html(invoice: InvoiceDetailResponse) -> str:
    """
    Build the standalone HTML document for one invoice's PDF export.

    Args:
        invoice: The assembled invoice detail to render.

    Returns:
        str: A complete HTML document ready for weasyprint.
    """
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>{_STYLE}</style>
</head>
<body>
  <h1>{_esc(invoice.brand_name)}</h1>
  <p class="subtitle">{_esc(invoice.site_name)}</p>

  <div class="meta">
    <div><strong>Invoice</strong><br>{_esc(str(invoice.id))}<br>{_esc(invoice.invoice_type.title())}</div>
    <div><strong>Date</strong><br>{invoice.created_at.strftime('%d %b %Y, %H:%M')}</div>
    <div><strong>Status</strong><br><span class="status">{_esc(invoice.status)}</span></div>
  </div>

  <table>
    <thead><tr><th>Item</th><th class="num">Qty</th><th class="num">Price</th><th class="num">Total</th></tr></thead>
    <tbody>{_line_item_rows(invoice)}</tbody>
  </table>

  {_tax_breakdown_table(invoice)}
  {_payments_table(invoice)}

  <table class="totals">
    <tbody>{_totals_rows(invoice)}</tbody>
  </table>
</body>
</html>
"""


def render_invoice_pdf(invoice: InvoiceDetailResponse) -> bytes:
    """
    Render an invoice's PDF export to raw bytes.

    Args:
        invoice: The assembled invoice detail to render.

    Returns:
        bytes: A complete PDF document.
    """
    return HTML(string=build_invoice_html(invoice)).write_pdf()
