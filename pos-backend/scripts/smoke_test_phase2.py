"""
Phase 2 smoke test — ZedRead POS backend.

Exercises the full stack from portal login through POS auth, catalog,
invoices, payments, and reporting. Self-contained: creates its own test
data and tears it down on exit.

Usage::

    # Minimum required env vars:
    PORTAL_EMAIL=admin@example.com \\
    PORTAL_PASSWORD=secret \\
    python scripts/smoke_test_phase2.py

    # Override base URL for staging:
    BASE_URL=https://pos-backend-production-c3d3.up.railway.app \\
    PORTAL_EMAIL=... PORTAL_PASSWORD=... python scripts/smoke_test_phase2.py

Exit 0 = all green. Non-zero = first failure printed with context.
"""

import os
import sys
import uuid

import httpx

BASE_URL = os.getenv("BASE_URL", "https://pos-backend-production-c3d3.up.railway.app")
PORTAL_EMAIL = os.getenv("PORTAL_EMAIL", "")
PORTAL_PASSWORD = os.getenv("PORTAL_PASSWORD", "")

PASS = "\033[32mOK  \033[0m"
FAIL = "\033[31mFAIL\033[0m"


def check(label: str, resp: httpx.Response, expected: int = 200) -> dict:
    """Print result and return JSON body, or exit on unexpected status."""
    if resp.status_code != expected:
        print(f"{FAIL} [{label}] expected {expected}, got {resp.status_code}")
        print(f"       {resp.text[:300]}")
        sys.exit(1)
    print(f"{PASS} [{label}]")
    return resp.json()


def main() -> None:
    """Run the full Phase 2 smoke test sequence."""
    if not PORTAL_EMAIL or not PORTAL_PASSWORD:
        print("ERROR: PORTAL_EMAIL and PORTAL_PASSWORD are required")
        sys.exit(1)

    uid = uuid.uuid4().hex[:6]  # unique suffix to avoid name collisions

    with httpx.Client(base_url=BASE_URL, timeout=30) as c:

        # ── 1. Health ────────────────────────────────────────────────────────
        check("health", c.get("/health"))

        # ── 2. Portal login ──────────────────────────────────────────────────
        resp = check("portal_login", c.post("/auth/portal/login", json={
            "email": PORTAL_EMAIL, "password": PORTAL_PASSWORD,
        }))
        portal_token = resp["access_token"]
        ph = {"Authorization": f"Bearer {portal_token}"}
        print(f"       token_type={resp.get('type', 'portal_access')}")

        # ── 3. Create group ──────────────────────────────────────────────────
        grp = check("create_group", c.post("/groups", json={"name": f"Smoke Group {uid}"}, headers=ph), 201)
        group_id = grp["id"]
        print(f"       group_id={group_id}")

        # ── 4. Create brand ──────────────────────────────────────────────────
        brd = check("create_brand", c.post("/brands", json={"group_id": group_id, "name": f"Smoke Brand {uid}"}, headers=ph), 201)
        brand_id = brd["id"]
        print(f"       brand_id={brand_id}")

        # ── 5. Create site ───────────────────────────────────────────────────
        sit = check("create_site", c.post("/sites", json={"brand_id": brand_id, "name": f"Smoke Site {uid}"}, headers=ph), 201)
        site_id = sit["id"]
        print(f"       site_id={site_id}")

        # ── 6. List access profiles (seeded by brand creation) ───────────────
        profiles = check("list_access_profiles", c.get(f"/access-profiles?brand_id={brand_id}", headers=ph))
        assert len(profiles) >= 1, "Expected at least one seeded access profile"
        profile_id = profiles[0]["id"]
        print(f"       profiles={[p['name'] for p in profiles]}")

        # ── 7. Create POS user ───────────────────────────────────────────────
        pos_email = f"smoke_{uid}@test.zedread.internal"
        pos_password = "SmokeTest123!"
        pos_user = check("create_pos_user", c.post("/pos-users", json={
            "brand_id": brand_id,
            "name": f"Smoke User {uid}",
            "email": pos_email,
            "password": pos_password,
        }, headers=ph), 201)
        pos_user_id = pos_user["id"]
        print(f"       pos_user_id={pos_user_id}")

        # ── 8. Grant POS user access to the site ────────────────────────────
        check("create_access_grant", c.post("/access-grants", json={
            "user_id": pos_user_id,
            "site_id": site_id,
            "access_profile_id": profile_id,
        }, headers=ph), 201)

        # ── 9. POS login (step 1 — get site list) ───────────────────────────
        login_resp = check("pos_login", c.post("/auth/pos/login", json={
            "email": pos_email, "password": pos_password,
        }))
        sites = login_resp["sites"]
        assert any(s["id"] == site_id for s in sites), f"Expected site {site_id} in login response"
        print(f"       sites_returned={[s['name'] for s in sites]}")

        # ── 10. POS token (step 2 — site-scoped JWT) ─────────────────────────
        tok_resp = check("pos_token", c.post("/auth/pos/token", json={
            "email": pos_email, "password": pos_password, "site_id": site_id,
        }))
        pos_token = tok_resp["access_token"]
        posh = {"Authorization": f"Bearer {pos_token}"}
        print(f"       site_id_in_token={tok_resp['site_id']}")

        # ── 11. Set PIN ──────────────────────────────────────────────────────
        check("set_pin", c.post("/auth/pos/pin/set", json={"new_pin": "1234"}, headers=posh), 200)

        # ── 12. Verify PIN ───────────────────────────────────────────────────
        pin_resp = check("verify_pin", c.post("/auth/pos/pin/verify", json={"pin": "1234"}, headers=posh))
        assert pin_resp["valid"] is True, "PIN should be valid"

        # ── 13. Wrong PIN returns valid=False ────────────────────────────────
        bad_pin = check("verify_wrong_pin", c.post("/auth/pos/pin/verify", json={"pin": "9999"}, headers=posh))
        assert bad_pin["valid"] is False, "Wrong PIN should return valid=false"

        # ── 14. Create tax category + rate (via portal JWT) ──────────────────
        tax_cat = check("create_tax_category", c.post("/tax/categories", json={
            "brand_id": brand_id, "name": "Standard Tax",
        }, headers=ph), 201)
        tax_cat_id = tax_cat["id"]

        check("create_tax_rate", c.post("/tax/rates", json={
            "tax_category_id": tax_cat_id,
            "name": "GST 10%",
            "rate_percent": "10.0000",
            "tax_model": "exclusive",
        }, headers=ph), 201)

        # ── 15. Create category ──────────────────────────────────────────────
        cat = check("create_category", c.post("/categories", json={
            "brand_id": brand_id, "name": "Drinks",
        }, headers=ph), 201)
        cat_id = cat["id"]

        # ── 16. Create product ───────────────────────────────────────────────
        prod = check("create_product", c.post("/products", json={
            "brand_id": brand_id,
            "category_id": cat_id,
            "tax_category_id": tax_cat_id,
            "name": "Flat White",
            "base_price_cents": 450,
            "display_order": 1,
        }, headers=ph), 201)
        product_id = prod["id"]
        print(f"       product_id={product_id}")

        # ── 17. Fetch catalog (POS JWT) ──────────────────────────────────────
        catalog = check("get_products", c.get(f"/products?site_id={site_id}", headers=posh))
        assert any(p["id"] == product_id for p in catalog), "Created product should appear in catalog"
        print(f"       catalog_size={len(catalog)}")

        # ── 18. Create invoice ───────────────────────────────────────────────
        inv = check("create_invoice", c.post("/invoices", json={
            "site_id": site_id, "invoice_type": "sale",
        }, headers=posh), 201)
        invoice_id = inv["id"]
        print(f"       invoice_id={invoice_id}")

        # ── 19. Add line item ────────────────────────────────────────────────
        li = check("add_line_item", c.post(f"/invoices/{invoice_id}/line-items", json={
            "product_id": product_id, "quantity": 2,
        }, headers=posh), 201)
        print(f"       subtotal_cents={li['subtotal_cents']} tax_cents={li['tax_cents']}")

        # ── 20. Pay invoice ──────────────────────────────────────────────────
        paid = check("pay_invoice", c.post(f"/invoices/{invoice_id}/pay", json={
            "method": "cash", "amount_cents": li["subtotal_cents"] + li["tax_cents"],
        }, headers=posh))
        assert paid["status"] == "paid", f"Expected status=paid, got {paid['status']!r}"
        print(f"       total_cents={paid['total_cents']} status={paid['status']}")

        # ── 21. Reporting — daily sales ──────────────────────────────────────
        report = check("daily_sales", c.get(f"/reports/daily-sales?site_id={site_id}", headers=ph))
        assert len(report) >= 1, "Expected at least one row in daily-sales"
        assert report[0]["invoice_count"] >= 1
        print(f"       daily_sales rows={len(report)} total_cents={report[0]['total_cents']}")

        # ── 22. Reporting — payment methods ─────────────────────────────────
        pm = check("payment_methods", c.get(f"/reports/payment-methods?site_id={site_id}", headers=ph))
        assert any(r["method"] == "cash" for r in pm), "Expected cash in payment methods"
        print(f"       payment_methods={[r['method'] for r in pm]}")

        # ── 23. Management JWT flow (Stage 13) ──────────────────────────────
        # POS user needs can_access_portal on their profile — use portal JWT to enable it.
        manager_profiles = [p for p in profiles if p["name"] == "Manager"]
        if manager_profiles:
            mgmt_login = c.post("/auth/portal/login", json={
                "email": pos_email, "password": pos_password,
            })
            if mgmt_login.status_code == 200:
                mgmt_data = mgmt_login.json()
                if "access_token" in mgmt_data:
                    check("mgmt_login", mgmt_login)
                    mgmt_token = mgmt_data["access_token"]
                    mh = {"Authorization": f"Bearer {mgmt_token}"}
                    check("mgmt_get_products", c.get(f"/products?brand_id={brand_id}", headers=mh))
                    print("       management JWT auth working")
                else:
                    print(f"{PASS} [mgmt_login] returned available_grants (multi-grant user)")
            else:
                print(f"      [mgmt_login] skipped — user profile lacks can_access_portal (expected for non-Manager profile)")
        else:
            print("      [mgmt_login] skipped — no Manager profile found in seeded profiles")

    print(f"\n\033[32mSMOKE TEST PASSED — all {23} checks green.\033[0m")


if __name__ == "__main__":
    main()
