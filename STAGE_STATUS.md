# ZedRead POS — Stage Build Status

Last updated: 2026-05-22

---

## Summary

| Phase | Stages | Status |
|-------|--------|--------|
| 1 — Foundation & Portal | 1–6 | ✅ Complete |
| 2 — POS Catalog | 7–9 | ✅ Complete |
| 3 — Transactions | 10–12 | ✅ Complete |
| 4 — Android App | 13–14 | 🚧 In Progress |

---

## Phase 1 — Foundation & Portal

### Stage 1 — Project Setup + Logging ✅

**Deliverables:**
- [x] `pos-backend/` folder structure (app/, tests/, alembic/)
- [x] Docker Compose: API + PostgreSQL (prod) + PostgreSQL (test) + Redis
- [x] SQLAlchemy async engine + session factory (`app/database.py`)
- [x] Alembic configured; migration `0001` creates `groups`, `brands`, `sites`, `audit_logs`
- [x] structlog setup: JSON renderer (prod) + ColourRenderer (dev), controlled by `LOG_FORMAT` env var
- [x] Request ID middleware: every request gets a UUID; all log lines carry `request_id`
- [x] `log_action()` helper written and unit-tested (`tests/unit/test_audit_service.py`)
- [x] `pytest.ini` + `conftest.py` with shared fixtures (test DB engine, rollback per test)
- [x] `requirements.txt` pinned

### Stage 2 — Portal Auth ✅

**Deliverables:**
- [x] Migration `0002` creates `portal_users`
- [x] `POST /auth/portal/login` — email + password → JWT
- [x] `POST /auth/portal/logout` — session revocation
- [x] Argon2 password hashing in `utils/security.py`
- [x] JWT encode/decode with role claim (`super_admin` / `admin` / `reseller`)
- [x] Bootstrap CLI: `python -m app.cli bootstrap-super-admin`
- [x] Auth audit logging: login and logout write `AuditLog` rows
- [x] Integration tests: `tests/integration/test_portal_auth_routes.py`

### Stage 3 — Hierarchy CRUD API ✅

**Deliverables:**
- [x] Groups CRUD: `GET /groups`, `POST /groups`, `PATCH /groups/{id}`, suspend/activate
- [x] Brands CRUD: `GET /brands`, `POST /brands`, `PATCH /brands/{id}`
- [x] Sites CRUD: `GET /sites`, `POST /sites`, `PATCH /sites/{id}`
- [x] All list routes: paginated (`skip`/`limit`), filtered by parent scope
- [x] All routes declare `response_model`
- [x] Audit logging on every create and status change
- [x] Human-readable ref IDs (`GRO-000001`, `BRA-000001`, `SIT-000001`) — added in migration `0013`
- [x] Integration tests: `test_groups_routes.py`, `test_brands_routes.py`, `test_sites_routes.py`

### Stage 4 — License Management ✅

**Deliverables:**
- [x] Migration `0004` creates `licenses`, `license_invoices`, `pos_devices`
- [x] Licenses CRUD + enable/disable endpoints
- [x] License invoices CRUD
- [x] POS device registration (`POST /pos-devices/register`) — requires active license; rejects duplicate `device_token` with 409
- [x] POS device deregistration (`DELETE /pos-devices/{id}`)
- [x] Nightly Celery task: expire licenses past `expires_at`; audit with `actor_type=system`
- [x] Audit logging on all license state changes
- [x] Unit tests: `tests/unit/test_license_tasks.py`
- [x] Integration tests: `test_license_routes.py`, `test_pos_device_routes.py`

### Stage 5 — Portal Frontend ✅

**Deliverables:**
- [x] React + TypeScript + Vite + Tailwind CSS project initialised (`pos-portal/`)
- [x] Axios client with JWT interceptors (`src/api/axios.ts`)
- [x] Auth context + `PrivateRoute` component
- [x] Portal pages:
  - [x] `LoginPage.tsx`
  - [x] `GroupsPage.tsx`
  - [x] `BrandsPage.tsx`
  - [x] `SitesPage.tsx`
  - [x] `LicensesPage.tsx`
  - [x] `PortalUsersPage.tsx`
  - [x] `PosUsersPage.tsx`
  - [x] `ChangePasswordPage.tsx`
  - [x] `brands/` sub-pages
  - [x] `management/` sub-pages
- [x] All tables have `overflow-x-auto` container for mobile
- [x] All pages tested at 375px viewport width

### Stage 6 — Deploy Phase 1 ✅

**Deliverables:**
- [x] API deployed to Railway with `Dockerfile`
- [x] `alembic upgrade head` runs on container startup
- [x] PostgreSQL on Supabase (production)
- [x] Portal deployed to Vercel
- [x] structlog → Grafana Cloud Loki connected
- [x] `railway.toml` configured

---

## Phase 2 — POS Catalog

### Stage 7 — POS Auth & Users ✅

**Deliverables:**
- [x] Migration `0005` creates `pos_users`, `user_pins`, `access_profiles`, `user_access_grants`
- [x] `POST /auth/pos/login` — email + password → JWT + site context
- [x] `POST /auth/pos/pin/set` — sets Argon2 PIN hash
- [x] `POST /auth/pos/pin/verify` — email + PIN + device_token → fresh JWT
- [x] POS user CRUD (`pos_users.py`)
- [x] Access profiles CRUD (`access_profiles.py`) — 4 system profiles auto-seeded per brand
- [x] User access grants CRUD (`access_grants.py`): scoped to site/brand/group, `is_default` support
- [x] `backend_role` on grants for portal management access — migrations `0017`, `0018`
- [x] User invite flow (`user_invites.py`, `user_invite_service.py`)
- [x] Management auth (`management_auth_service.py`, `test_management_auth_routes.py`)
- [x] Audit logging: POS login, logout, failed login, PIN set, PIN reset
- [x] Integration tests: `test_pos_auth_routes.py`, `test_access_grants.py`
- [x] Unit tests: `test_access_profile_seeding.py`, `test_security.py`

### Stage 8 — Product Catalog ✅

**Deliverables:**
- [x] Migration `0006` creates `tax_categories`, `tax_rates`, extends `products`, `site_product_overrides`
- [x] Migration `0003` creates `categories` (system "Uncategorised" auto-created per brand)
- [x] Products CRUD (`products.py`, `product_service.py`): paginated, soft-delete, brand-scoped
- [x] Product photo upload to Supabase Storage (max 500 KB, enforced in service)
- [x] Tax categories + rates CRUD (`tax.py`, `tax_service.py`)
- [x] Tax calculation service: inclusive / exclusive / compound (`tax_calculation_service.py`)
- [x] Site product overrides (`site_overrides.py`, `site_override_service.py`)
- [x] `product_resolver.py` merges brand catalog with site overrides at query time
- [x] Audit logging: product created, updated, price changed, deactivated
- [x] Integration tests: `test_product_routes.py`, `test_tax_routes.py`, `test_site_override_routes.py`
- [x] Unit tests: `test_tax_calculation.py`, `test_product_resolver.py`

### Stage 9 — Variants, Modifiers, Combos ✅

**Deliverables:**
- [x] Migration `0007` creates `product_variants`, `product_attribute_types`, `product_attribute_values`, `product_variant_attributes`
- [x] Migration `0008` creates `modifier_groups`, `modifier_options`, `product_modifier_group_links`, `product_combo_groups`, `product_combo_options`
- [x] Variants CRUD (`variants.py`, `variant_service.py`)
- [x] Modifier groups + options CRUD (`modifiers.py`, `modifier_service.py`)
- [x] Combo products CRUD (`combos.py`, `combo_service.py`) with circular reference detection
- [x] Site variant overrides (`site_variant_overrides`)
- [x] Integration tests: `test_variant_routes.py`, `test_modifier_routes.py`, `test_combo_routes.py`
- [x] Unit tests: `test_variant_service.py`

---

## Phase 3 — Transactions

### Stage 10 — Invoice Engine ✅

**Deliverables:**
- [x] Migration `0009` creates `invoices`, `invoice_line_items`, `invoice_line_modifiers`, `invoice_tax_breakdowns`, `payments`
- [x] `POST /invoices` — create draft invoice
- [x] `POST /invoices/{id}/line-items` — add product line (snapshots all price/tax fields)
- [x] `POST /invoices/{id}/line-items/{lid}/modifiers` — add modifier
- [x] `POST /invoices/{id}/apply-discount` — apply discount with reason
- [x] `POST /invoices/{id}/pay` — record payment; auto-transitions to `paid` when sum covers total
- [x] `POST /invoices/{id}/void` — requires manager permission; sets `voided_at`
- [x] `POST /invoices/{id}/refund` — creates a new `invoice_type=refund` row with `status=paid`
- [x] Split payment support (multiple `Payment` rows per invoice)
- [x] Invoice status machine: `draft → open → paid | voided`
- [x] Audit logging: invoice paid, voided, refunded, discount applied
- [x] Integration tests: `test_invoice_routes.py` (15+ scenarios)

### Stage 11 — Reporting ✅

**Deliverables:**
- [x] Migration `0010` creates 8 PostgreSQL views (`vw_daily_sales`, `vw_product_revenue`, `vw_payment_methods`, `vw_tax_collected`, `vw_hourly_sales`, `vw_modifier_popularity`, `vw_invoice_detail`, `vw_refund_summary`)
- [x] `GET /reports/daily-sales`
- [x] `GET /reports/product-revenue`
- [x] `GET /reports/payment-methods`
- [x] `GET /reports/tax-collected`
- [x] `GET /reports/hourly-sales`
- [x] `GET /reports/modifier-popularity`
- [x] `GET /reports/invoice-detail`
- [x] `GET /reports/refund-summary`
- [x] All routes filter by `brand_id` / `site_id` scope from JWT
- [x] All routes paginated with `skip` / `limit`
- [x] Integration tests: `test_report_routes.py`

### Stage 12 — Deploy Phase 2 ✅

**Deliverables:**
- [x] All 50+ backend routes deployed and smoke-tested on Railway
- [x] `scripts/` directory with smoke tests
- [x] Performance indexes on common filter columns — migration `0012`
- [x] Full test suite passing (unit + integration)

---

## Phase 4 — Android App

### Stage 13 — Android Auth & Catalog 🚧

**Deliverables:**
- [x] Android project initialised: Kotlin + Jetpack Compose + Hilt + Retrofit + Room
- [x] Project structure: `data/`, `di/`, `ui/screens/`, `ui/components/`, `ui/viewmodel/`, `ui/theme/`
- [x] Screen scaffolding exists for: `auth/`, `cart/`, `catalog/`, `payment/`, `switchuser/`
- [x] `PosNavHost.kt` navigation graph
- [x] Backend: Migration `0011` adds access grants table extensions for management access
- [ ] POS login screen (email + password)
- [ ] PIN entry screen
- [ ] Site selector screen (for users with multi-site access)
- [ ] Product grid screen (category tabs + product tiles)
- [ ] Cart screen (line items, modifiers, quantity)
- [ ] Retrofit API client wired to backend endpoints
- [ ] Room local cache for catalog (offline-capable browsing)
- [ ] Hilt DI modules for network, database, repositories

### Stage 14 — Android Payments & Printing 🔜

**Deliverables:**
- [ ] Payment screen (cash / card / voucher / split)
- [ ] Docket/receipt printing (`printing/` module scaffolded)
- [ ] Switch user flow (PIN re-entry without full logout)
- [ ] End-of-day summary screen
- [ ] Invoice history screen
- [ ] Error handling + offline sync reconciliation
- [ ] APK build + signing configuration

---

## Cross-Cutting — Always Active

| Concern | Status |
|---------|--------|
| Audit logging (every write) | ✅ Complete through Stage 12 |
| Structured JSON logging (structlog) | ✅ Complete |
| Request ID middleware | ✅ Complete |
| Test coverage — integration | ✅ 22 integration test files |
| Test coverage — unit | ✅ 7 unit test files |
| Mobile-responsive portal (375px) | ✅ Applied to all portal pages |
| Monetary values as cents (BIGINT) | ✅ Enforced throughout |
| Constants from `app/constants/` | ✅ No hardcoded strings |

---

## Known Gaps & Technical Debt

| Item | Location | Priority |
|------|---------|---------|
| Circular combo reference: no DB constraint | `combo_service.py` graph traversal only | Low |
| Photo size limit: no DB constraint | `product_service.py` check only | Low |
| Invoice line `notes` column: not exposed in API | `invoice_line_items.notes` exists in model | Low |
| Split payment: backend done, Android UI pending | Stage 14 | High |
| Offline sync strategy: not documented | Android Stage 13–14 | High |
| Tax compound edge cases (PST on GST): not validated | `tax_calculation_service.py` | Medium |
| Accounting/journal integration for refunds | Not started | Future |
