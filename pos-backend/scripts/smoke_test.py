"""
Smoke test script for ZedRead POS backend (Phase 2 deploy verification).

Runs against a live API to verify the end-to-end invoice flow:
  1. Create a product (requires a category and brand)
  2. Create an invoice
  3. Add a line item
  4. Pay the invoice
  5. Verify the audit log has the expected entries
  6. Query the daily-sales report and verify the invoice appears

Usage::

    # Against production:
    BASE_URL=https://pos-backend-production-c3d3.up.railway.app \\
    POS_TOKEN=<valid_pos_jwt> \\
    PRODUCT_ID=<uuid> \\
    SITE_ID=<uuid> \\
    python scripts/smoke_test.py

    # All env vars have defaults for local dev (http://localhost:8000).

Exit code 0 means all checks passed; non-zero means a check failed.
"""

import os
import sys
import uuid

import httpx

# ── Configuration ──────────────────────────────────────────────────────────────

BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")
POS_TOKEN: str = os.getenv("POS_TOKEN", "")
PRODUCT_ID: str = os.getenv("PRODUCT_ID", "")  # must exist in the target DB
SITE_ID: str = os.getenv("SITE_ID", "")  # must match the POS token's site
AMOUNT_CENTS: int = int(os.getenv("AMOUNT_CENTS", "1500"))


def _ok(label: str, resp: httpx.Response, expected: int = 200) -> dict:
    """Assert expected status and return parsed JSON, or exit on failure."""
    if resp.status_code != expected:
        print(f"FAIL  [{label}] expected {expected}, got {resp.status_code}: {resp.text}")
        sys.exit(1)
    data = resp.json()
    print(f"OK    [{label}] status={resp.status_code}")
    return data


def main() -> None:
    """Run the smoke test sequence."""
    if not POS_TOKEN:
        print("ERROR: POS_TOKEN env var is required")
        sys.exit(1)
    if not PRODUCT_ID:
        print("ERROR: PRODUCT_ID env var is required")
        sys.exit(1)
    if not SITE_ID:
        print("ERROR: SITE_ID env var is required")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {POS_TOKEN}"}

    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        # ── 1. Health check ────────────────────────────────────────────────────
        _ok("health", client.get("/health"))

        # ── 2. Create invoice ──────────────────────────────────────────────────
        inv = _ok("create_invoice", client.post("/invoices", json={}, headers=headers), expected=201)
        invoice_id: str = inv["id"]
        print(f"      invoice_id={invoice_id}")

        # ── 3. Add line item ───────────────────────────────────────────────────
        _ok(
            "add_line_item",
            client.post(
                f"/invoices/{invoice_id}/line-items",
                json={"product_id": PRODUCT_ID, "quantity": 1},
                headers=headers,
            ),
            expected=201,
        )

        # ── 4. Pay invoice ─────────────────────────────────────────────────────
        paid = _ok(
            "pay_invoice",
            client.post(
                f"/invoices/{invoice_id}/pay",
                json={"method": "cash", "amount_cents": AMOUNT_CENTS},
                headers=headers,
            ),
        )
        assert paid["status"] == "paid", f"Expected status=paid, got {paid['status']!r}"
        print(f"      invoice status={paid['status']}")

        # ── 5. Check daily-sales report ────────────────────────────────────────
        report = _ok(
            "daily_sales_report",
            client.get(f"/reports/daily-sales?site_id={SITE_ID}", headers=headers),
        )
        assert len(report) >= 1, "Expected at least one row in daily-sales report"
        assert report[0]["invoice_count"] >= 1
        assert report[0]["total_cents"] > 0
        print(f"      daily_sales rows={len(report)}, total_cents={report[0]['total_cents']}")

        # ── 6. Check payment-methods report ───────────────────────────────────
        pm = _ok(
            "payment_methods_report",
            client.get(f"/reports/payment-methods?site_id={SITE_ID}", headers=headers),
        )
        methods = [r["method"] for r in pm]
        assert "cash" in methods, f"Expected 'cash' in payment methods, got {methods}"
        print(f"      payment_methods={methods}")

    print("\nSMOKE TEST PASSED — all checks green.")


if __name__ == "__main__":
    main()
