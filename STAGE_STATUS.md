# ZedRead POS — Stage Build Status

Last updated: 2026-07-07

---

## Summary

| Phase | Stages | Status |
|-------|--------|--------|
| 1 — Foundation & Portal | 1–6 | ✅ Complete |
| 2 — POS Catalog | 7–9 | ✅ Complete |
| 3 — Transactions | 10–12 | ✅ Complete |
| 4 — Identity & Permissions Redesign | 15 | ✅ Complete |
| 5 — Catalog Foundations | 16–18 | 🚧 In Progress (Stages 16–17 complete) |
| 6 — Catalog Data & Table UX | 19–20 | 🔜 Planned |
| 7 — Invoices & Extended Catalog | 21–22 | 🔜 Planned |
| 8 — POS Menu Builder | 23 | 🔜 Planned |
| 9 — Product Model Extensions | 24 | ✅ Complete |
| 10 — Android App | 25–26 | 🚧 In Progress (scaffolding only) |

Stage numbers 13–14 are retired — the Android phase is renumbered to 25–26 to make room for
Stages 16–24, which were planned after Android scaffolding had already begun.

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
- [x] Portal deployed to Railway
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

## Phase 4 — Identity & Permissions Redesign

### Stage 15 — Rename + 5-Role Model ✅

**Deliverables:**
- [x] `app/constants/pages.py` — 17-page catalog across 5 categories (Product & Menus, App
  Configuration, Reports, User Management, Customers & Loyalty)
- [x] `AccessProfilePagePermission` model + `access_profile_service.py` grant/revoke/resolve functions
- [x] `app/constants/license_plans.py` — per-tier page allowlists (starter/pro/enterprise)
- [x] Routes: `GET/POST /access-profiles/{id}/pages`, `DELETE .../{page_key}`, `GET .../visible-pages`
- [x] `POST /auth/portal/identity-token` — cross-identity (SuperAdmin vs User) login disambiguation
- [x] Backend rename: `portal_users` → `superadmins` (migration `0020`), `pos_users` → `users`
  (migration `0021`)
- [x] Required-field rules for Users (first/last name, PIN, email+password gating on backend access)
- [x] Portal frontend rename: nav/routes/components renamed to SuperAdmins (`/superadmins`) and
  Users (`/users`); `isPortalUser` → `isSuperAdmin`, `PortalUser` type → `SuperAdmin` (`Layout.tsx`,
  `AuthContext.tsx`, `PrivateRoute.tsx`, `App.tsx`, `SuperAdminsPage.tsx`, `UsersPage.tsx`)
- [ ] Portal UI for page permissions — no page calls the access-profile-pages endpoints yet
  (closed out in Stage 18)

---

## Phase 5 — Catalog Foundations

### Stage 16 — Reporting Groups ✅

**Deliverables:**
- [x] Migration `0038`: `reporting_groups` table (brand-scoped), `ref` sequence (`RPG-000001`)
- [x] System default reporting group seeded per brand (existing brands backfilled by the
  migration; new brands seeded atomically in `brand_service.create_brand()`), undeletable
- [x] `categories.reporting_group_id` — NOT NULL FK, backfilled to each brand's default group
- [x] Category create/update requires `reporting_group_id` (prompted in portal, auto-assigned to
  the brand's default in `category_service.py` if omitted on create)
- [x] Reporting Groups CRUD routes + service (`reporting_group_service.py`,
  `routes/reporting_groups.py`), blocks deleting the default group or one still referenced by
  categories
- [x] Portal: new "Reporting Groups" sidebar page (`ReportingGroupsPage.tsx`), plus a required
  Reporting Group select added to the Category create/edit modal
- [x] `reporting_groups` page key added to `PAGE_CATALOG`, default role grants, license-tier page
  sets, and `ROLE_MODEL.md` §6
- [x] `categories.py` refactored into thin routes + `category_service.py`; fixed a pre-existing bug
  where category audit rows used `PRODUCT_CREATED`/`PRODUCT_UPDATED` instead of the dedicated
  `CATEGORY_CREATED`/`CATEGORY_UPDATED` constants
- [x] Integration tests: `test_reporting_group_routes.py`, `test_categories_routes.py`

### Stage 17 — Delegated User Creation ✅

**Deliverables:**
- [x] Scope ladder was already enforced (`access_grant_service._assert_create_authority`, Stage 13);
  this stage adds the missing **role ceiling**: `_assert_role_ceiling()` compares the rank of the
  profile being granted against the rank of the caller's own access profile
  (`access.access_profile`, resolved from the grant they authenticated with) and rejects with 403 if
  the target outranks them. Rank ladder (`_ROLE_RANK` in `access_grant_service.py`): Staff <
  Reporting Only < Manager < Admin < Master User. A custom (non-system) profile's real permission
  breadth can't be inferred from its name, so it is conservatively ranked at the Admin tier on both
  sides of the comparison — see the in-code comment for the reasoning.
- [x] Master User is now unconditionally ungrantable through `POST/PATCH /access-grants` — checked
  for *every* caller, including portal admins — since it must stay a single, auto-created,
  immutable identity per site (`site_service.create_site()` is the only path that creates it).
- [x] Applied to both grant creation and grant update (`access_profile_id` changes), since both are
  ways to hand someone a higher access level.
- [x] Rejected attempts write no audit row (not a state change) but structlog a `WARNING` with the
  caller's and target's profile names for traceability, per the stage plan.
- [x] `GET /access-profiles` — previously portal-admin-only — now also accepts management JWTs,
  scoped to the caller's own brand (site/brand-scope) or any brand in their group (group-scope), so
  the portal's role-picker can be populated without leaking other tenants' profile catalogs.
- [x] Portal: `management/UsersPage.tsx` gained a "Grant Access" form (this page previously only
  listed/revoked grants, with no creation UI at all). Scope options and the profile dropdown are
  filtered client-side to what the logged-in management user may grant — the 403 guards above are
  the actual enforcement; the UI filtering only avoids showing choices that would be rejected.
- [x] Integration tests: 14 new cases in `test_access_grants.py` (brand-scope and group-scope role
  ceiling, Master User rejection for both management and portal callers, update-grant ceiling, no
  audit row on rejection, and the widened `/access-profiles` scope checks).

**Known limitation:** the create-grant form takes the target user's ID and the site/brand ID as raw
UUID text input rather than searchable dropdowns, because no existing management-JWT-scoped route
lists sites/brands/users today (`/sites`, `/brands`, `/users` are all portal-admin-only) — adding
those was out of scope for this stage. Flagged for Stage 18 or a follow-up if a friendlier picker is
wanted.

### Stage 18 — Permission Scopes Portal UI 🔜

**Deliverables:**
- [ ] Portal page: list access profiles per scope, toggle page-level permission grants
- [ ] License-gated pages shown disabled/greyed-out with reason, not silently omitted
- [ ] Reconcile CLAUDE.md Stage 15 note and ensure ROLE_MODEL.md §6 stays in sync going forward

---

## Phase 6 — Catalog Data & Table UX

### Stage 19 — Bulk Import/Export (XLSX) 🔜

**Deliverables:**
- [ ] Surface dormant `products.ref` / `categories.ref` columns (migration `0013`) into ORM model + schema
- [ ] Shared `export_service.py` / `import_service.py`: template export, filtered full export, validate-then-upsert import
- [ ] Products/Categories/Reporting Groups import matches existing rows by `ref`; partial-update
  semantics (only columns present in the uploaded header row are changed)
- [ ] Template export includes data-validation dropdowns for category/reporting-group columns
- [ ] Each import writes one `audit_logs` row per changed record, grouped by a batch `import_id`

### Stage 20 — Table UX 🔜

**Deliverables:**
- [ ] Products table: Reporting Group + Category columns (via join, no denormalization)
- [ ] Inline cell edit on Products/Categories/Reporting-Groups tables
- [ ] Filter bar (category, reporting group, active/inactive, text search) reused across all three pages
- [ ] Filter bar `flex-wrap`s at 375px (CLAUDE.md rule 16)

---

## Phase 7 — Invoices & Extended Catalog

### Stage 21 — Invoice Reporting 🔜

**Deliverables:**
- [ ] Invoice list filters (date range, site, payment status, amount range) + XLSX export via Stage 19 framework
- [ ] Invoice detail view: line items, modifiers, tax breakdown, payments
- [ ] Change-log panel sourced from `audit_logs` filtered by `entity_type='invoice'` (already
  populated by `invoice_service.py` — no new table)
- [ ] PDF export: standard invoice layout (recommend `weasyprint`, HTML/CSS-authored layout — no
  existing PDF generation to match style against)

### Stage 22 — Variants & Combos Portal Pages 🔜

**Deliverables:**
- [ ] `ref` sequences for Variants (`VAR-000001`) and Combos (`CMB-000001`)
- [ ] `display_name` field on `Variant` and `Combo` (not Modifiers — Modifiers stay edited inline on
  the Product page, no separate sidebar entry)
- [ ] Combined portal page: Variants + Combos in one sidebar entry, filters (by product, active state),
  inline edit, import/export via Stage 19 framework
- [ ] Product page/table shows linked variants; Variant page shows its linked product

---

## Phase 8 — POS Menu Builder

### Stage 23 — Menu Builder Prototype 🔜

**Deliverables:**
- [ ] Migration: `menu_layouts` (scope, name, `is_published`, version), `menu_tabs` (ordered),
  `menu_buttons` (tab_id, product `ref` code — not FK, so a button survives product recreation)
- [ ] Portal builder UI: drag/drop tabs and buttons, live name/price preview from the catalog by code
- [ ] Publish warns if a button's code no longer resolves to an active product
- [ ] Multiple layouts may be published at once (e.g. per-site or day-part menus)
- [ ] `GET /pos/menu-layout?site_id=` contract for Android to consume (Android consumption is out of
  scope for this stage)
- [ ] Prototype scope: single-level tabs + buttons only, no nested sub-menus

---

## Phase 9 — Product Model Extensions

### Stage 24 — Product Extensions ✅

**Deliverables:**
- [x] `products.ref` wired into ORM model + schema as "product code" (migration `0037`)
- [x] `print_name` column (nullable, falls back to `name`; `effective_print_name` computed property/response field)
- [x] `is_open_item` flag; flexible price/name at time of sale, defaulting to the product's own fields
  (Android sale-time UI itself is out of scope — data model only)
- [x] `can_use_open_item` capability flag + optional `open_item_max_price_cents` ceiling on `AccessProfile`
  (a capability flag, not a page grant — it's an action permission, not a page); exposed via
  `PATCH /access-profiles/{id}/capabilities`
- [x] Photo upload cap raised 500 KB → 1 MB; 500x500 minimum resolution enforced (422 if smaller);
  1:1 ratio surfaced as portal UI guidance only, not a hard rule
- [x] `description` and `photo_url` already exist on Product — no work needed

---

## Phase 10 — Android App

### Stage 25 — Android Auth & Catalog 🚧

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

### Stage 26 — Android Payments & Printing 🔜

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
| Split payment: backend done, Android UI pending | Stage 26 | High |
| Offline sync strategy: not documented | Android Stage 25–26 | High |
| Tax compound edge cases (PST on GST): not validated | `tax_calculation_service.py` | Medium |
| Accounting/journal integration for refunds | Not started | Future |
