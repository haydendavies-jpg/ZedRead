# ZedRead POS — Stage Build Status

Last updated: 2026-07-13 (Menu Studio redesign — POS Layout grid editor, Phase 2)

---

## Summary

| Phase | Stages | Status |
|-------|--------|--------|
| 1 — Foundation & Portal | 1–6 | ✅ Complete |
| 2 — POS Catalog | 7–9 | ✅ Complete |
| 3 — Transactions | 10–12 | ✅ Complete |
| 4 — Identity & Permissions Redesign | 15 | ✅ Complete |
| 5 — Catalog Foundations | 16–18 | ✅ Complete |
| 6 — Catalog Data & Table UX | 19–20 | ✅ Complete |
| 7 — Invoices & Extended Catalog | 21–22 | ✅ Complete |
| 8 — POS Menu Builder | 23 | ✅ Complete |
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

### Stage 18 — Permission Scopes Portal UI ✅

**Deliverables:**
- [x] New portal page `management/AccessProfilesPage.tsx` at `/management/access-profiles`
  ("Permission Scopes" in the sidebar, `MGMT_BRAND_NAV` — brand/group scope, same `ScopeGuard
  minScope="brand"` as Users & Grants): lists an brand's access profiles as a pill selector, and for
  the selected profile renders every `PAGE_CATALOG` page grouped by category with a checkbox wired
  to the existing `GET/POST /access-profiles/{id}/pages` and `DELETE .../pages/{page_key}` routes
  (built in Stage 15, unused by the frontend until now) — no backend changes were needed.
- [x] License-gated pages are never hidden. Where a site context is available, a granted-but-
  license-blocked page shows a "License-gated" badge (tooltip explains why) computed from `GET
  .../visible-pages?site_id=` — a page in the granted set but absent from the resolved visible set
  is blocked purely by the site's license plan. The toggle itself stays interactive either way,
  since the grant and the license gate are independent axes (ROLE_MODEL.md §4): revoking a
  license-gated page is still a real, useful action.
- [x] Site context for the preview: SuperAdmins get a "Preview site" dropdown (they can call
  `GET /sites?brand_id=`); a site-scope management user's own site is read straight from their JWT.
- [x] `PAGE_CATALOG` / `PAGE_CATEGORY_LABELS` mirrored client-side in `types/index.ts` for rendering
  (page_key validity is still enforced server-side on grant/revoke) — extends the Stage 18 standing
  rule: every future stage that ships a portal page now updates three places in the same commit:
  `app/constants/pages.py`, `ROLE_MODEL.md` §6, and this frontend mirror.

**Known limitation:** brand/group-scope management users (unlike SuperAdmins and site-scope
management users) have no route to resolve a specific site to preview the license gate against —
`/sites` and `/licenses` are both portal-admin-only, and Stage 17 already flagged the lack of a
management-JWT-scoped sites list as a gap. For those callers the page shows a plain notice instead
of a preview; the grant/revoke toggles work regardless, since license gating only affects whether a
User's session can actually see a page, not whether an admin may grant it. Revisit if a
management-scoped `GET /sites` (or similar) is added for another stage.

---

## Phase 6 — Catalog Data & Table UX

### Stage 19 — Bulk Import/Export (XLSX) ✅

**Deliverables:**
- [x] Surfaced the dormant `categories.ref` column (migration `0013`) into the ORM model and
  `CategoryOut` schema — `products.ref` was already wired in Stage 24, `reporting_groups.ref` in
  Stage 16, so all three entities now expose their human-readable code.
- [x] Shared `app/services/export_service.py` (template + full-export workbook building, per-entity
  query + row-mapping functions, hidden-sheet data-validation dropdowns) and
  `app/services/import_service.py` (XLSX parsing, value coercion, validate-then-upsert per row) —
  built once, reused across Products, Categories, and Reporting Groups; the same two modules are
  designed to be reused again for Variants/Combos in Stage 22.
- [x] Products/Categories/Reporting Groups import matches existing rows by `ref`; a blank `ref`
  creates a new record via the same `*Create` schema and service function the direct API uses.
  Partial-update semantics: only columns present in the uploaded header row are touched — routed
  through the existing `update_product()`/`update_category()`/`update_reporting_group()` service
  functions (all their existing validation, 403 system-record protection, and audit logging is
  reused unchanged, not reimplemented).
- [x] Row-level validate-then-upsert: each row is validated independently; a bad row (unresolvable
  category/reporting-group name, unknown `ref`, bad type) is skipped and reported in
  `ImportSummary.errors` with its row number, rather than failing the whole upload.
- [x] Template export: header row + one example row + an Excel data-validation dropdown (category
  names for Products, reporting-group names for Categories) sourced from a hidden helper sheet
  (a literal inline list is capped at 255 characters, too small for real catalogs). Full export
  carries the brand's current data with the same dropdowns attached so it stays re-importable.
- [x] Each import writes one `audit_logs` row per changed record via the entity's existing
  create/update service (`PRODUCT_CREATED`/`PRODUCT_UPDATED`/`CATEGORY_CREATED`/... — no new audit
  action constants), all rows from one upload sharing a batch `import_id` (a fresh UUID per call)
  embedded in `after_state` — no new column/table needed, since `audit_logs.after_state` is already
  a JSONB free-form field.
- [x] New `set_product_active_state()` in `product_service.py`: import-only, idempotent
  activate/deactivate (the existing `deactivate_product()` 409s on a repeat call, which would
  misreport an unchanged row in a re-uploaded sheet as an error). Added `PRODUCT_REACTIVATED` audit
  constant for the reactivate-via-import case, since no portal route exposes that today.
- [x] Routes: `GET /{resource}/export/template`, `GET /{resource}/export`, `POST /{resource}/import`
  on `products.py`, `categories.py`, `reporting_groups.py` — thin, all logic in the two shared
  services. `response_model=None` declared explicitly on the two GET routes (binary `.xlsx` download,
  not a JSON payload a Pydantic model could describe).
- [x] `openpyxl==3.1.5` added to `requirements.txt`.
- [x] Unit tests: `test_export_service.py`, `test_import_service.py` (workbook assembly, XLSX
  parsing, value coercion — no database). Integration tests:
  `test_product_import_export_routes.py`, `test_category_import_export_routes.py`,
  `test_reporting_group_import_export_routes.py` (template/export downloads, create-by-import,
  update-by-import partial semantics, row-level error reporting, system-record protection, audit
  rows carrying `import_id`, auth failures, invalid-file 422).

**Known limitation:** "respecting whatever filters are active on the page" for the full export is
deferred to Stage 20 — that stage's filter bars don't exist yet, so `GET /{resource}/export`
currently exports all of the brand's rows unconditionally (matching what `list_*` already returns
without filters). Revisit once Stage 20 ships filter query params.

### Stage 20 — Table UX ✅

**Deliverables:**
- [x] Products table: Reporting Group + Category columns, resolved via a join in
  `product_service.list_products()` (`select(Product, Category.name, Category.reporting_group_id,
  ReportingGroup.name).join(...)`) — not denormalized onto the `products` row, so a category's
  reporting-group reassignment is reflected immediately with no sync-drift risk. New
  `ProductListItem` response schema (`app/schemas/product.py`) extends `ProductResponse` with
  `category_name` / `reporting_group_id` / `reporting_group_name`, used only by `GET /products`.
- [x] `GET /products` and `GET /categories` gained `include_inactive` (default `False`, back-compat
  preserved) so the Stage 20 table views can fetch the full active+inactive set once and filter
  active/inactive client-side, matching the portal's established client-side-filtering convention
  (no repeat API calls per filter change).
- [x] New `POST /products/{id}/activate` route reusing the existing (Stage 19) idempotent
  `set_product_active_state()` service function — needed once inactive products became visible in
  the table, so there had to be a way back. Categories already supported reactivation via the
  existing `PATCH /categories/{id} {is_active: true}` path (`update_category()`), no backend change
  needed there.
- [x] Inline cell edit — click-to-edit for text/number cells (`EditableText`), always-inline commit-
  on-change for dropdowns (`EditableSelect`), both in `pos-portal/src/components/EditableCell.tsx`.
  Wired up alongside (not replacing) the existing modal-based create flow, per the stage plan:
  - Products: Name, Category (select), Price (inc.) inline; Reporting Group is read-only in the
    row (derived through Category, no direct FK to edit); Status is a clickable `StatusBadge` that
    calls the DELETE (deactivate) or new activate route. The "Edit" modal remains for
    description/tax-mode/open-item fields that have no table column.
  - Categories: Name and Reporting Group inline (both disabled for system categories); Status
    toggle disabled for system categories (matches the existing 403 rule). The old separate
    rename modal is gone — nothing was left for it to do once both its fields became inline-editable
    — only the create modal remains.
  - Reporting Groups: Name inline (disabled for the system default group). Same simplification —
    the old rename modal is gone, only create + delete remain.
  - `StatusBadge` (`pos-portal/src/components/StatusBadge.tsx`) gained an optional `onClick`/
    `disabled` — renders as a button only when a handler is passed, so its many existing read-only
    usages (Groups/Brands/Sites/Licenses/Users) are unaffected.
- [x] Shared `FilterBar` component (`pos-portal/src/components/FilterBar.tsx`): free-text search
  (matches name or `ref` code) + any number of labeled select filters + a "Clear filters" link + an
  `X of Y` count chip, following the label-above-control convention already established on
  `SitesPage.tsx`. Reused as-is across Products (category, reporting group, status filters),
  Categories (reporting group, status filters), and Reporting Groups (type filter). All filtering is
  client-side against the already-fetched list, consistent with every other portal list page.
  `flex flex-wrap` on the bar's outer container — verified at 375px (CLAUDE.md rule 16).
- [x] `pos-portal/src/types/index.ts` — `Category` was missing `ref`; `Product` had drifted from
  `ProductResponse` (stale `sku`/`created_at` fields that don't exist on the backend schema; missing
  `ref`/`print_name`/`effective_print_name`/`is_open_item`/`photo_url`). Both fixed, plus the new
  `ProductListItem` type for the joined list-row shape.
- [x] Backend integration tests: `test_product_routes.py` (joined columns present on list rows,
  `include_inactive` default-excludes/includes, `/activate` reactivates + is idempotent + writes
  `PRODUCT_REACTIVATED`), `test_categories_routes.py` (`include_inactive` default-excludes/includes).

**Known limitation:** the portal has no Import/Export UI yet for the Stage 19 XLSX routes (no
"Export"/"Import" buttons exist on any of the three pages — Stage 19 only built the backend). The
stage plan's note that "full export uses active filters" therefore doesn't apply yet: there's no
export button to wire a filter query string into. Revisit if/when the Stage 19 XLSX routes get a
portal entry point — until then `GET /{resource}/export` continues to export the brand's full
unconditional set, and the Stage 20 filter bars remain client-side-only against the already-fetched
list, matching how every other portal list page filters.

---

## Phase 7 — Invoices & Extended Catalog

### Stage 21 — Invoice Reporting ✅

**Deliverables:**
- [x] `app/services/invoice_report_service.py` (new — split out of the transactional
  `invoice_service.py`, which stays engine-only): `list_invoice_reports()` reads the Stage 11 view
  `vw_invoice_detail` with a parameterised filter builder (site, date range on `created_at::date`,
  status, `total_cents` min/max) — the CLAUDE.md-documented exception to "always use the ORM" since
  reporting views are raw-SQL by nature; `get_invoice_detail()` assembles the full invoice (line
  items with nested modifiers, tax breakdown, payments) via the ORM; `get_invoice_change_log()` reads
  `audit_logs` filtered by `entity_type='invoice', entity_id=<id>`, oldest first.
- [x] Fixed a gap in `create_refund()` (`invoice_service.py`): it previously wrote its
  `INVOICE_REFUNDED` audit row only against the *new* refund invoice's `entity_id`, so the original
  invoice's change log never showed it had been refunded. It now also logs a second row against the
  original invoice's own `entity_id` (`before_state={is_refunded: false}`,
  `after_state={is_refunded: true, refund_invoice_id: ...}`), so the Stage 21 plan's claim that
  "invoice_service.py already writes a row... for pay, void, refund, discount" against `entity_id=<id>`
  is now actually true for refunds, not just pay/void/discount.
- [x] Read-only `export_invoices()`/`build_invoices_export()` added to Stage 19's shared
  `export_service.py` — same filter set as the list route, so "export the filtered set" produces
  exactly what's on screen. No `import_invoices()` counterpart: invoices are created by the sale
  flow, not bulk-uploaded, so only the workbook-building half of the Stage 19 framework applies.
- [x] `app/services/invoice_pdf_service.py` (new): standard single-invoice layout authored as
  HTML/CSS and rendered via `weasyprint` (no existing PDF style to match, per the stage plan's
  recommendation over a programmatic library like `reportlab`). All interpolated text is
  HTML-escaped. Added `weasyprint==63.1` to `requirements.txt`; CI installs the Pango/Cairo/
  GDK-Pixbuf system libraries weasyprint needs at runtime (`.github/workflows/ci.yml`).
- [x] New router `app/routes/invoice_reports.py`, prefix `/invoice-reports`, registered in
  `main.py` alongside (not replacing) the existing `/invoices` transactional routes: `GET` (filtered
  list), `GET /export` (XLSX), `GET /{id}` (detail), `GET /{id}/change-log`, `GET /{id}/pdf`. Uses
  `resolve_catalog_access` like `reports.py`, so POS, management, and portal-admin tokens all work;
  site-pinned callers (POS terminal, site-scope management) are restricted to their own site the same
  way `reports.py`'s `_check_site_access` works.
- [x] Portal: new `InvoicesPage.tsx` (`/management/invoices`) — server-side filters (site, status,
  date range, min/max total) posted as query params so the XLSX export matches what's on screen,
  plus an Export XLSX button using a new `downloadBlob()` helper (`utils/download.ts`). New
  `InvoiceDetailPage.tsx` (`/management/invoices/:invoiceId`) — line items with nested modifiers, tax
  breakdown, payments, a change-log table, and a Download PDF button. Both reachable from `MGMT_NAV`
  and as a new "Invoices" tab on the SuperAdmin's `BrandDetailPage` (mirroring the existing "Reports"
  tab) — the brand tab is the SuperAdmin's only entry point since `MGMT_NAV` is management-JWT-only;
  the "View"/"Back" links append `?brand_id=` when known so navigating out of `BrandContext` into the
  standalone detail route doesn't lose scope.
- [x] Integration tests: `test_invoice_reports_routes.py` (list filters incl. status/amount-range/
  site-scope 403, detail view, XLSX export column shape, PDF export magic-bytes/content-type, change
  log incl. the refund-on-original-invoice fix, 401/404 paths). Unit tests:
  `test_invoice_pdf_service.py` (HTML generation, HTML-escaping of product names, discount-reason
  rendering — no database, no rendering).

### Stage 22 — Variants & Combos Portal Pages ✅

**Deliverables:**
- [x] `ref` sequences for Variants (`VAR-000001`) and Combos (`CMB-000001`) — migration `0039`, same
  mechanism as migration `0013`/Stage 16. There is no standalone `Combo` table in the schema; a
  "combo product" is just a `Product` that owns one or more `product_combo_groups` rows, so
  `ProductComboGroup` is the entity Stage 22 surfaces as "Combo" in the portal.
- [x] `display_name` column on `ProductVariant` and `ProductComboGroup` (nullable, falls back to the
  attribute-derived label / the existing POS-facing `name` respectively when unset) — not on
  Modifiers, which stay edited inline on the Product page per the resolved decision in
  `STAGE_PLAN_16-24.md` §22.
- [x] `ProductComboGroup` also gained `is_active` (migration `0039`) to reach parity with
  `product_variants.is_active`, plus the update/deactivate/reactivate service functions and routes
  it previously lacked (`update_combo_group()`, `deactivate_combo_group()` — 409 on repeat, mirrors
  `deactivate_variant()` — and `set_combo_group_active_state()` — idempotent, mirrors
  `product_service.set_product_active_state()`). `ProductVariant` gained the matching
  `set_variant_active_state()` idempotent function and `POST .../variants/{id}/activate` route (it
  already had `deactivate_variant()` from Stage 9), so both entities get the same status-toggle
  table UX as Products (Stage 20).
- [x] Inline schemas that used to live in `variant_service.py`/`combo_service.py` (Stage 9's
  "keep the footprint small" choice) extracted into `app/schemas/variant.py`/`app/schemas/combo.py`
  now that both files have grown well past that stage's scope.
- [x] New brand-wide `GET /variants` / `GET /combos` (on a second `list_router` in each of
  `routes/variants.py`/`routes/combos.py`, alongside the existing product-nested `router`) — each
  joins to the parent `Product` for a `product_name`/`product_ref` pair on every row
  (`list_variants_for_brand()`/`list_combo_groups_for_brand()`), so the combined portal page can
  browse across the whole catalog rather than one product at a time. Both support `product_id` and
  `include_inactive` filters.
- [x] Bulk XLSX export/import extended onto Stage 19's shared `export_service.py`/`import_service.py`:
  `VARIANT_COLUMNS`/`COMBO_COLUMNS` keyed on `ref` + a `product_ref` column (product refs are
  guaranteed unique per brand, unlike names, so there's no ambiguity resolving the linked product on
  import). Variant import is **update-only** — a blank `ref` is reported as a row error rather than
  creating a variant, since attribute assignment varies per brand and doesn't fit a fixed spreadsheet
  header (and no portal page manages attribute types to begin with — that gap predates this stage).
  Combo import supports both create (via `product_ref`) and update (via `ref`), since
  `ComboGroupCreate`'s fields are all plain scalars.
- [x] Portal: new `VariantsCombosPage.tsx` (`/management/variants-combos`) — one sidebar entry, two
  tabs (Variants / Combos), each with the shared `FilterBar` (search, linked-product filter, status
  filter), inline edit (`EditableText` for display name; SKU/price on Variants; name/display name on
  Combos), a `StatusBadge` activate/deactivate toggle, and the portal's first Import/Export XLSX UI
  (download template, export, upload-to-import with an inline created/updated/errors summary) — the
  Stage 19 routes had no portal entry point anywhere until this stage. Combos also get an "Add combo"
  modal (product picker + name/display name/selection rules); Variants have no create flow here for
  the same attribute-assignment reason import can't create them — see the product page instead.
  Reachable from `MGMT_NAV` and as a new tab on the SuperAdmin's Brand detail page.
- [x] Product ↔ Variant cross-linking (portal-only, no schema change beyond what's above): the
  Product edit modal's new read-only "Variants" section lists that product's variants
  (`GET /products/{id}/variants`) with a link into the combined page; the combined page's Variants
  tab already shows each row's linked product (name + ref chip), covering "Variant shows its linked
  product" without a separate variant detail route.
- [x] Integration tests: 11 new cases across `test_variant_routes.py`/`test_combo_routes.py` — ref/
  display_name on create, idempotent activate + `variant.reactivated`/`combo_group.reactivated`
  audit rows, combo group update/deactivate/409-on-repeat, brand-wide list joins, import update/
  create/error-row paths (blank ref, unknown `product_ref`) with `import_id` asserted on the
  resulting audit row.

**Known limitation:** there is still no portal page for managing per-brand attribute types/values
(Stage 9 shipped the backend only). Until one exists, Variants can be created only via the API
directly, not the portal or an XLSX import — flagged here rather than built speculatively, since
it's a Stage 9 gap this stage didn't introduce.

---

## Phase 8 — POS Menu Builder

### Stage 23 — Menu Builder Prototype ✅

**Deliverables:**
- [x] Migration `0040`: `menu_layouts` (`brand_id`, nullable `site_id`, `scope` — 'brand' or 'site'
  with a check constraint tying the two together, `name`, `is_published`, `version`), `menu_tabs`
  (`layout_id`, `name`, `display_order`), `menu_buttons` (`tab_id`, `product_ref` — a product's `ref`
  code, deliberately not a FK, so a button survives the underlying product being deleted and
  recreated with the same code, per the original ask). New models `MenuLayout`/`MenuTab`/`MenuButton`
  registered in `app/models/__init__.py`.
- [x] `app/services/menu_builder_service.py`: CRUD for layouts/tabs/buttons, tab and button reorder
  (a single `POST .../buttons/reorder` call reassigns `tab_id` and renumbers `display_order` for a
  full ordered id list, so a cross-tab drag only needs one call against the destination tab),
  `publish_menu_layout()` (bumps `version`, resolves every button's `product_ref` against the brand's
  catalog and returns a `PublishWarning` per stale/inactive ref **without** blocking the publish, per
  the stage plan's "warn (don't silently fail)"), `unpublish_menu_layout()`, and
  `get_published_menu_layouts_for_site()` — the read model behind the POS contract below. All writes
  call `log_action()` with new `MENU_LAYOUT_*`/`MENU_TAB_*`/`MENU_BUTTON_*` audit constants.
- [x] New router `app/routes/menu_layouts.py`: `/menu-layouts` (management/portal JWT only, mirroring
  `reporting_groups.py`'s `_require_management` guard — POS terminal tokens are read-only via the
  contract route) covers layout CRUD, publish/unpublish, tab CRUD + reorder, button add/remove +
  reorder; a second `pos_router` exposes `GET /pos/menu-layout?site_id=` — the Android consumption
  contract (Android-side consumption itself is explicitly out of scope for this stage) — reusing
  `report_service._assert_site_scope()` so POS terminal and site-scope management tokens are pinned
  to their own site the same way `reports.py` already works.
- [x] `menu_builder` page key added to `PAGE_CATALOG` (Product & Menus category), `ROLE_MODEL.md` §6,
  and `PRO_PLAN_PAGES` in `license_plans.py` (Manager/Admin/Master get it by default via the existing
  `PAGE_KEYS`-derived grants; Staff does not), per the Stage 18 standing rule that every new portal
  page updates all three places in the same commit.
- [x] Portal: new `MenuBuilderPage.tsx` (`/management/menu-builder`) — a layout list (create, open,
  publish/unpublish toggle via `StatusBadge`, delete) plus a builder view: a draggable tab sidebar
  and a draggable button grid, both using native HTML5 drag-and-drop (no new dependency — none was
  installed in this project) rather than pulling in a dnd library for a single-level reorder/move
  use case. Buttons show a live name/price preview resolved from the brand's catalog by `product_ref`
  and flag in red when a code no longer resolves (matching the publish-warning reasons). Reachable
  from `MGMT_NAV` and as a new tab on the SuperAdmin's Brand detail page.
- [x] Prototype scope honoured: single-level tabs + buttons only, no nested sub-menus. More than one
  layout may have `is_published=True` at once (e.g. per-site or day-part menus) — publishing one
  layout has no effect on any other.
- [x] Integration tests: `test_menu_layout_routes.py` (29 cases — layout/tab/button CRUD, tab and
  button reorder including a cross-tab move, publish with/without warnings on a since-deactivated
  product, unpublish, brand/site scope validation incl. a foreign-brand `site_id` rejection, auth
  failures, the `/pos/menu-layout` contract incl. published-only filtering and site-scope 403, and
  audit rows for `MENU_LAYOUT_CREATED`/`MENU_TAB_CREATED`/`MENU_BUTTON_ADDED`/`MENU_LAYOUT_PUBLISHED`).

**Known limitation:** creating a `scope='site'` layout still has no site picker for brand/group-scope
management users or SuperAdmins outside a Brand-detail-page context — the same gap Stage 17/18 already
flagged (no management-JWT-scoped `GET /sites` route exists). A site-scope management user's own
`site_id` is read straight from their JWT and pre-filled automatically; anyone else must paste the
target site's UUID into a raw text field, mirroring the identical workaround already shipped on
`management/UsersPage.tsx`'s grant-creation form. Revisit both together if a management-scoped sites
list is ever added.

### Menu Studio visual/functional redesign — Table view + Menus (partial pass) 🚧

Implemented from a Claude-designed HTML mockup (`design_handoff_menu_studio/`). Explicitly scoped
with the user to the **Table view** (Products/Modifiers/Categories) and the new **Menus** screen —
the POS Layout grid editor redesign (drag/resize/multi-select tiles, active-time/day scheduling) is
a separate, larger follow-up and was not attempted here; `MenuBuilderPage.tsx`/`menu_layouts` are
unchanged from Stage 23.

**Deliverables:**
- [x] Migration `0041`: `categories.default_color` (hex, POS button colour default); new
  `modifier_option_group_links` table (self-referential through `modifier_groups` via a
  `ModifierOption` — "comboing"); new `menus` table + `menus_ref_seq` (`MNU-000001`).
- [x] `modifier_service.py`: `list_modifier_groups_detailed()` (nested groups→options→linked
  groups, one level deep, plus a used-by-product count), `link_option_group()`/`unlink_option_group()`,
  `deactivate_modifier_group()`/`deactivate_modifier_option()` (soft-delete — didn't exist before),
  `duplicate_modifier_group()`. New routes on `modifiers.py`: `GET /modifier-groups/detailed`,
  `POST /modifier-groups/{id}/duplicate`, `DELETE /modifier-groups/{id}`,
  `DELETE /modifier-options/{id}`, `POST /modifier-options/{id}/links`,
  `DELETE /modifier-options/{id}/links/{group_id}`.
- [x] `menu_service.py` + new router `menus.py` (`/menus`, management/portal JWT only): CRUD,
  duplicate, schedule/cancel-schedule/publish. Reuses `menu_layouts`' brand-vs-site `scope`
  assignment pattern; `menu_layout_id` optionally links a Menu to the POS button layout it activates.
- [x] `product_service.list_products()` now also resolves each row's category colour and a
  comma-joined list of active linked modifier group names via a correlated subquery (no
  denormalization) — `ProductListItem.category_color`/`modifier_names`.
- [x] `menus` page key added to `PAGE_CATALOG`/`ROLE_MODEL.md` §6/`license_plans.py` (pro tier),
  per the Stage 18 standing rule; the new Modifiers portal page reuses the existing
  `variants_modifiers` key rather than adding a new one.
- [x] Portal: `ThemeContext.tsx` (portal-wide light/dark mode, `dark` class on `<html>`, toggle in
  the sidebar footer); redesigned `CategoriesPage.tsx` (reporting-group-grouped cards, colour
  swatch popover via new `ColorSwatchPicker.tsx`, floating bulk-assign bar, inline add-forms); new
  `ModifiersPage.tsx` (cards, inline nested-cascade comboing UI — no modifier management page
  existed before this); `ProductsPage.tsx` gained a category-colour dot and a Modifiers column;
  new `MenuStudioPage.tsx` (Table/POS Layout segmented control wrapping
  Products/Modifiers/Categories, POS Layout delegating unchanged to `MenuBuilderPage`); new
  top-level `MenusPage.tsx`. `MGMT_NAV` updated accordingly (old standalone Products/Categories/
  Menu Builder nav entries replaced by Menu Studio + Menus; their routes/components still exist,
  used directly by `BrandDetailPage`'s own tabs). `Source Serif 4`/`IBM Plex Mono` wired as
  Tailwind's `font-serif`/`font-mono`; pre-existing pages got a mechanical `dark:` companion-class
  sweep rather than a hand-tuned pass — see `pos-portal/CLAUDE.md`.
- [x] Integration tests: `test_menu_routes.py`, `test_modifier_comboing_routes.py`, plus additions
  to `test_categories_routes.py` for `default_color` — happy path, auth failure, invalid input,
  business rules (foreign-brand site, self-link rejection, duplicate link 409, scheduling a
  published/past-dated menu, cancelling a non-scheduled menu), and audit log assertions for every
  new write action.

**Deferred to a follow-up pass (now delivered — see below):** the POS Layout grid editor. The
`Menus` screen's literal register/channel assignment remains deferred — it still reuses
`menu_layouts`' site-scope pattern, since no register/channel entity exists.

### Menu Studio visual/functional redesign — POS Layout grid editor (Phase 2) ✅

Implemented from the same design mockup's POS Layout screens, previously deferred. Delivers the
graphical grid editor the Stage 23 prototype's single-level tab/button list stood in for.

**Deliverables:**
- [x] Migration `0042`: `menu_layouts` gains `color` (hex, list/rail dot), `published_at`,
  active-time/day-of-week scheduling (`is_all_day`/`start_time`/`end_time`/`active_days`, distinct
  from `is_published` — controls when a *published* layout is visible on the POS, e.g. a Breakfast
  layout only 7am–11am) and `scheduled_publish_at` (the "Schedule publish" bulk action — persisted
  only, same known no-Celery-job limitation as the `Menus` entity's own schedule field). `menu_tabs`
  gains a self-referential `parent_tab_id` (unbounded nesting — tabs can drill into tabs) and its
  own `color`. `menu_buttons` gains `kind` (`'product'` | `'folder'` — a folder button opens a
  nested `MenuTab` instead of a product; `product_ref` becomes nullable to make room),
  `child_tab_id`, `width`/`height` (1-6 × 1-4 grid-cell span; no x/y — the 6-column CSS grid packs
  tiles via `grid-auto-flow: dense`), and an optional `color` override falling back to the linked
  product's category default colour. Check constraints enforce kind/field consistency and the
  width/height ranges.
- [x] `menu_builder_service.py` rewritten: tab loading is now flat across all nesting depths (the
  portal builds the rail/breadcrumb from `parent_tab_id`); `list_menu_layouts()` returns each
  layout's total button count via a correlated subquery; `duplicate_menu_layout()` deep-copies the
  full tab tree + buttons via a two-pass id-remap (tabs first, then buttons, so folder
  `child_tab_id`s point at the copies); `schedule_layout_publish()`/`cancel_layout_scheduled_publish()`
  (400 on a past target time); `update_menu_button()` (resize/recolor/relink — `color` is checked via
  `model_fields_set` rather than `is not None` so an explicit `{"color": null}` clears an override
  back to the category default, the same idiom `access_grant_service.update_grant` already uses for
  `backend_role`); `bulk_recolor_menu_buttons()`/`bulk_delete_menu_buttons()`/
  `group_menu_buttons_into_tab()` (the multi-select floating action bar's recolor/delete/"Group into
  tab" — all three require every selected button share one source tab, 400 otherwise);
  `_layout_active_now()` (best-effort UTC check — `Site.timezone` isn't validated zoneinfo, flagged
  in the docstring) now gates `get_published_menu_layouts_for_site()` alongside `is_published`.
- [x] `routes/menu_layouts.py` rewritten to match: `POST .../duplicate`, `POST
  .../schedule-publish`, `POST .../cancel-schedule-publish`, `PATCH .../buttons/{id}`, `POST
  .../buttons/bulk-recolor`, `POST .../buttons/bulk-delete`, `POST .../buttons/group-into-tab`; list
  route unpacks the new `(MenuLayout, button_count)` tuple shape.
- [x] Portal: `MenuBuilderPage.tsx` rewritten — layouts list (colour dot, button count, Published/
  Unpublished pill, active-time + day-of-week chip, last-published/last-edited timestamps,
  Edit/Duplicate/Delete/Publish-Unpublish/Hours/Schedule-publish actions) and a grid editor (rail of
  top-level tabs with a "+ Add tab"; breadcrumb; 6-column dense CSS grid with a trailing dashed "+"
  tile; pointer-based click/shift-click multi-select and drag-move dropping onto a rail tab or
  folder tile — `elementFromPoint().closest('[data-drop]')`, mirroring the mockup's technique — with
  a "Moving N button(s)" cursor-following ghost label; corner-handle live resize (1-6 × 1-4);
  multi-select floating action bar — palette + custom colour recolor, "Move to" dropdown, "Group
  into tab", "Delete", "Clear"; single-selection inspector — live preview, linked-product dropdown or
  rename+"Open tab" for a folder, colour palette + custom + "Category default" reset, width/height
  steppers, "Delete button"). Reuses `ColorSwatchPicker`'s `MENU_STUDIO_PALETTE`/`textColorOn` rather
  than duplicating them. `Import`/`Export` pills shown in the original mockup are intentionally
  omitted — no export/import backend exists for `menu_layouts` (unlike Products/Categories/Reporting
  Groups' Stage 19 `export_service.py`), and a non-functional button would violate the
  no-half-finished-features rule; revisit if layout import/export is ever scoped.
- [x] Integration tests: `test_menu_layout_editor_routes.py` — folder buttons creating/cascading a
  nested tab, button resize/recolor/relink incl. the explicit-null colour-reset case, bulk
  recolor/delete/group-into-tab incl. the mixed-source-tab 400, duplicate deep-copying tabs+buttons,
  schedule/cancel-schedule-publish incl. the past-time 400, the active-time window update incl. its
  `is_all_day=False`-without-times 400, and the `/pos/menu-layout` contract now also excluding/
  including a layout by its active-time window (previously only tested `is_published`). The existing
  `test_menu_layout_routes.py` (Stage 23) suite needed no changes — the new columns/fields all carry
  defaults, so the prototype-era assertions still hold.

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
