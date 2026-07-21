# ZedRead POS — Stage Build Status

Last updated: 2026-07-21 (Android exact-match Register screen + invoice line-item update/remove — see ANDROID_POS_BUILD_PLAN.md)

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
| 10 — Android App | 25–26 | 🚧 In Progress — see `ANDROID_POS_BUILD_PLAN.md` |

Stage numbers 13–14 are retired — the Android phase is renumbered to 25–26 to make room for
Stages 16–24, which were planned after Android scaffolding had already begun.

---

## Descoped features

**Site overrides (removed 2026-07-14).** The per-site price/availability override feature built in
Stages 8–9 was removed — the implementation was not right and will be rescoped later. Dropped:
`site_product_overrides` / `site_variant_overrides` tables (migration `0044`), their ORM models,
`site_override_service.py`, `product_resolver.py` (`resolve_products_for_site()` / `ResolvedProduct`),
the `/site-overrides` router + resolved-catalog endpoint, the `SITE_PRODUCT_OVERRIDE_*` audit actions,
their tests, and the portal `SiteOverridesPage` (management nav entry + Brand detail tab). The Stage 8
and Stage 9 checklists below still list these items as originally delivered; this note supersedes them.

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

### Menu Studio — user-testing feedback round 2 ✅

Nine reported issues fixed in one pass:

- [x] **Blank page after adding a user (SuperAdmin portal)** — two stacked bugs. The create form
  still sent the legacy `name` field, but `POST /users` has required `first_name`/`last_name` since
  Stage 15's model split, so every create 422'd; and the 422's array-of-objects `detail` was stored
  in state and rendered raw, crashing React ("Objects are not valid as a React child") and
  unmounting the whole app — the "blank page". `UsersPage.tsx`'s create/edit forms now use
  First/Last name fields (`UserOut` gained `first_name`/`last_name` so the edit modal pre-fills
  accurately; edit previously sent `name` too, which the backend silently ignored — renames never
  applied), and every raw `e?.response?.data?.detail` in `UsersPage.tsx`/`management/UsersPage.tsx`/
  `LoginPage.tsx` was swept to the existing 422-safe `apiErrorMessage()` helper.
- [x] **"New modifier" slow to respond** — the card only appeared after the full
  `/modifier-groups/detailed` refetch. `createGroup`/`createOption` now append the POST response to
  the query cache immediately (background invalidate still reconciles), the button shows
  "Creating…", and `patchGroup`/`patchOption` apply optimistic cache updates with rollback-on-error,
  so checkbox/min-max/name/price edits reflect instantly rather than after a round trip.
- [x] **Modifier groups couldn't be renamed** — the card title is now a commit-on-blur
  `BufferedInput` wired to the existing `PATCH /modifier-groups/{id}` (backend already supported it).
- [x] **Quantity option on modifiers** — new `modifier_groups.has_quantity` flag (migration `0043`,
  default false = old once-per-option behaviour): when true the POS may select the same option more
  than once (per-option quantity), still capped by the group's `max_selections` in total. Exposed
  through create/update/response schemas, the detailed listing, and duplication (copies the flag);
  portal shows a "Quantity" checkbox beside "Required". POS-side enforcement is Android-stage work —
  this ships the data model + management UI.
- [x] **Category/reporting-group add delay** — same cache-append-from-response pattern as the
  modifier fixes, plus an "Adding…" pending label.
- [x] **POS Layout: empty slots + "+ Row"** — the grid now pads with dashed "+" slots to full rows
  of 6 (an empty tab shows one full row of 6, matching the mockup's default), each opening the
  product picker; a "+ Row" toolbar button adds another row of 6 (per-tab, visual only — empty
  slots are not persisted). Max 6 per row was already enforced by the 6-column grid.
- [x] **POS Layout: insertion bar between buttons** — while dragging, hovering a tile's outer 25%
  edges (or anywhere over a product tile) shows a brand-coloured insertion bar and dropping
  repositions the dragged button(s) at that boundary via the existing reorder route; only a folder
  tile's middle 50% still means "drop into the folder" — fixing the reported "trying to swap a
  product and a group just drops the product into the group".
- [x] Tests: `has_quantity` create-default/update+audit/duplicate-copies cases added to
  `test_modifier_routes.py`; every flow above manually verified end-to-end with Playwright against
  real dev servers (user create/rename, modifier create timing ~125ms to visible, rename+quantity
  persistence across reload, 6/12 slot counts, edge-drop reorder vs centre-drop into folder).

---

### Performance — request latency optimization (all portal/POS actions) ✅

Diagnosed a reported 5–10 s delay on every portal action. Root cause: **per-request database
round-trip amplification** — the auth dependencies in `app/utils/dependencies.py` issued 4–6
*sequential* queries (user → grant → profile → scope entities, or user → site → grant → profile →
session) before the route's own work, so a simple PATCH sent ~11–12 sequential statements
(auth + route query + audit INSERT + UPDATE + COMMIT + refresh + pool pre-ping). Each statement
costs a full network RTT to the database; with the API and database in different regions this
compounds into seconds on *every* click, and the portal's invalidate-and-refetch after each
mutation pays it twice. Measured per-request statement counts (SQLAlchemy event listener against
the real test DB) before → after:

| Request | Before | After |
|---|---|---|
| `GET /products` (management JWT) | 5 | 2 |
| `GET /products` (POS JWT) | 6 | 2 |
| `POST /products` (management JWT) | 10 | 7 |
| `PATCH /products/{id}` (management JWT) | 8 | 5 |

- [x] **Single-round-trip auth resolution** — new `_load_pos_context()` / `_load_mgmt_context()`
  loaders (one LEFT-OUTER-joined SELECT each) replace the sequential chains in `resolve_access`,
  `resolve_management_access`, and both inline branches of `resolve_catalog_access` (which had
  duplicated the logic). Error order, status codes, and messages are preserved — NULL columns from
  the outer joins map onto the exact same 401/403/500 branches.
- [x] **Request duration telemetry** — `RequestLoggingMiddleware` now logs `duration_ms` on
  `request.completed`, emits a `request.slow` WARNING at ≥1000 ms, and returns an
  `X-Response-Time-Ms` header so client-observed latency can be split into server time vs network
  time from the browser dev tools alone.
- [x] **Event-loop protection** — `GET /invoice-reports/{id}/pdf` ran WeasyPrint (CPU-bound,
  seconds) directly on the event loop, stalling every concurrent request; now `asyncio.to_thread`.
- [x] **Pool tuning** — `DB_POOL_SIZE` (default 10), `DB_MAX_OVERFLOW` (10), and
  `DB_POOL_RECYCLE_SECONDS` (1800) env vars on the engine; recycling pre-empts the remote pooler's
  idle timeout so requests don't pay a failed-ping + full TLS reconnect.
- [x] Tests: `X-Response-Time-Ms` header assertions added to `test_request_id.py`; full backend
  suite green (auth behaviour covered by the existing pos/management/catalog auth suites).
- [ ] **Deployment follow-up (not code)**: the remaining fixed cost is RTT × ~2–7 statements — if
  the Railway service and the Supabase project are in different regions, co-locating them is the
  single biggest win available (turns every remaining round trip from ~150–300 ms into ~1–5 ms).
  Compare the `duration_ms` now in Railway logs against browser-observed latency to confirm.
  Confirmed post-merge: Railway was US West (California) and Supabase Northeast Asia (Seoul) —
  the plan is Railway → Southeast Asia (Singapore) now, Supabase → `ap-southeast-1` when a
  migration window allows.

---

### Menu Studio — feedback round 3 ✅

Six reported issues fixed in one pass:

- [x] **Products couldn't attach modifiers** — the `product_modifier_group_links` table existed
  (Stage 9) with attach/detach routes but no frontend consumer. Added `GET /products/{id}/modifiers`
  (attached, ordered by `display_order`, + available) and `PATCH /products/{id}/modifiers/reorder`
  (reconciles membership and resequences `display_order` for the whole set in one transaction —
  `sync_product_modifier_groups()` in `modifier_service.py`, mirroring `reorder_menu_buttons()`'s
  whole-list-resequence pattern). Portal: the Modifiers cell on `ProductsPage.tsx` is now clickable,
  opening a new `ModifierPickerModal.tsx` — an "attached, drag to reorder" list (native HTML5 drag)
  above an "add more" checklist of the brand's other active groups, "Done" calling the reorder route
  with the full ordered set.
- [x] **No bulk multi-select/edit on Products** — `ProductsPage.tsx` gained a checkbox column
  (header select-all/indeterminate) and a floating bulk-action bar. New `POST /products/bulk`
  (`ProductBulkUpdate` schema, `bulk_update_products()` in `product_service.py`) applies any
  combination of category, price (absolute or `price_markup_percent` — multiplies each selected
  product's *current* price via `Decimal`/`ROUND_HALF_UP`, never float, per CLAUDE.md rule 9), tax
  category, one modifier-group attach (append-only, never detaches), and archive/reactivate to a
  selected set in one all-or-nothing transaction; every product_id/category_id/tax_category_id/
  modifier_group_id is validated against the caller's brand up front (400 with the offending ids,
  mirroring `import_service.py`'s validate-then-upsert convention) before any row is touched. One
  `log_action()` row is written per product actually changed, so each product's own audit trail
  stays complete. **There is no bulk "Reporting Group" action** — reporting group is derived through
  Category (`categories.reporting_group_id`), not a Product column, so bulk category assignment
  already changes a product's effective reporting group; adding a separate override column was
  explicitly decided against to avoid diverging from that model. The Reporting Group *column* was
  also dropped from the Products table for the same reason (the filter stays, since it's still a
  useful lever).
- [x] **No real archive action, and archiving left stale references behind** — `is_active=False`
  was already soft-delete-only (there is no hard-delete route), but archiving previously left a
  product's modifier links and any POS-layout buttons pointing at it dangling. The bulk-archive path
  above (and any future single-product archive reusing the same service call) now cascades:
  `_cascade_deactivate_products()` deletes every `product_modifier_group_links` row for the archived
  products, and every `menu_buttons` row (`kind='product'`) across the brand's `menu_layouts` whose
  `product_ref` matches one of them (scoped via `tab_id → menu_tabs.layout_id → menu_layouts.brand_id`,
  since `menu_buttons` has no direct brand column). `StatusBadge` on `ProductsPage.tsx` now reads
  active/archived with "Click to archive"/"Click to reactivate" titles.
- [x] **No way to add products to a modifier group from the modifier side** — `ModifiersPage.tsx`'s
  static "Used by N product(s)" line is now a toggle that expands into the actual product list
  (name, an inactive badge where relevant) via a new `GET /modifier-groups/{id}/products`
  (`list_products_for_modifier_group()`, reusing the same join `used_by_count` already used), lazily
  fetched only while expanded. An inline "+ Add product" select (populated from the brand's products
  not already linked) calls the *existing* `POST /products/{product_id}/modifiers` route from this
  side, optimistically patching the expanded list and the group's `used_by_count` in cache.
- [x] **POS Layout: could only drop between existing tiles, not onto an empty cell** —
  `menu_buttons` gained nullable `grid_col`/`grid_row` (migration `0045`; null = unchanged auto-pack-
  by-`display_order` fallback, set = explicit absolute grid position) and a new
  `PATCH /menu-layouts/buttons/{id}/place` route (`place_menu_button()`, clamps to the 6-column
  bound, no overlap enforcement — dense-pack/CSS resolves minor overlaps visually, and strict
  rejection would make quick drags error-prone). Portal: the grid's dashed "+" empty-slot tiles now
  carry a `data-drop="cell:<tab>:<col>:<row>"` target wired through the existing pointer-drag
  machinery, so a product tile, a folder tile, or the click-to-add-product flow can all target a
  specific empty cell instead of only appending to the end of the tab's ordered list; a button with
  an explicit `grid_col`/`grid_row` renders at that absolute position, everything else keeps the
  prior dense auto-pack layout.
- [x] **POS Layout: 5-10s lag on every drag/resize/recolor/add/group-into-tab** — root-caused (this
  round, not the earlier general "request latency optimization" pass, which fixed a different,
  auth-dependency-shaped problem) to every `GridEditor` mutation calling
  `invalidateQueries({ queryKey: ['menu-layout', layoutId] })` on success, forcing a full refetch of
  the entire tab tree + every button + product-ref resolution regardless of how small the actual
  change was. Several menu-layout mutation routes/services were broadened to return the full
  resolved object they touched (not a bare id/204) so the frontend could patch its cache instead:
  `update_menu_button`, `create_menu_button`, `reorder_menu_buttons`, `bulk_recolor_menu_buttons`,
  `bulk_delete_menu_buttons`, `group_menu_buttons_into_tab`, plus the new `place_menu_button`. Every
  `GridEditor` mutation (move/place, resize/recolor/relink, add product/folder, delete (incl. folder
  → descendant-tab cascade computed from the cached tree), reorder/drag-move, rename tab, bulk
  recolor/delete, group-into-tab, publish/unpublish) now patches the `['menu-layout', layoutId]`
  cache directly from its own response — `invalidateQueries` remains only as the `onError` rollback
  path, never on the success path, so no single-button interaction pays for a whole-tree reload.
- [x] Tests: `test_product_modifiers_routes.py`, `test_product_bulk_routes.py` (reorder/reconcile
  correctness, bulk price/markup/category/tax, bulk-archive cascade asserting both the modifier
  links and menu_buttons rows are actually gone, brand-scope rejection, per-product audit rows);
  extended `test_menu_layout_editor_routes.py` (`/place` grid-bounds validation, cross-tab move,
  audit row, broadened response shapes). Full backend suite (734 tests) green; portal typecheck
  (`tsc -p tsconfig.app.json --noEmit`, `tsc -b --noEmit`) clean.

---

### Menu Studio — feedback round 3 follow-up ✅

Two issues reported after the round-3 merge, on the same POS Layout grid editor:

- [x] **Dropping a button onto an occupied tile still only "slotted between" buttons, never onto the tile itself.** Root cause: `handlePointerDownTile`'s hover detection treated *any* position over a non-folder tile as an insertion target (`!isFolderTile || relX < 0.25 || relX > 0.75` was always true for a product tile, since `!isFolderTile` alone satisfies it) — there was no code path that ever resolved to "drop directly onto this tile," only "insert beside it." Fixed by scoping insertion to the tile's outer 25% edges for *every* tile kind, and giving the center 50% of a non-folder tile a new `'button'` drop-target kind: dropping there now swaps the dragged button and the tile's occupant into each other's exact grid cells via two `PATCH .../place` calls (`swapOntoButton()`, `computeCellForButton()` — the latter reuses the same running width×height offset already used to compute empty "+" slot coordinates when a button has no explicit `grid_col`/`grid_row` yet). Both gestures — slot-between (edges) and drop-onto/swap (center) — are now reachable on the same tile.
- [x] **Still-slow moves.** `reorder_menu_buttons()` and `place_menu_button()` — both fired on every single drag — carried avoidable extra round trips: `reorder_menu_buttons` re-fetched the destination tab and re-selected its buttons from the database *after* already committing the very same (in-memory, now-committed) rows moments earlier, instead of just reusing them; `place_menu_button` called `db.refresh(button)` even though every field `MenuButtonOut` reads was already assigned in Python before the commit and none of them are server-generated. Removed both redundant round trips — under this project's already-documented RTT-bound deployment (Railway US-West / Supabase Seoul, not yet co-located per the earlier "request latency optimization" round's deployment follow-up), each avoided round trip is a full network hop, so this directly compounds with that known, still-outstanding regional-latency gap rather than being a separate bug.
- [x] Tests: full backend suite (746 tests) green; portal typecheck (`tsc -p tsconfig.app.json --noEmit`) clean. Not covered: no browser-driven verification of the drag gestures was performed this session.

---

### Menu Studio — grid coordinate correctness fix + tab delete ✅

A screen recording of the previous follow-up's swap-onto-tile fix surfaced the actual root cause
behind three symptoms the user reported as one thing ("movement is finicky"): tiles landing in the
wrong place after a drop, a tile ending up "on top of" (painted over, not deleted — confirmed by
frame-by-frame review) another tile, and a persistently-highlighted drop target with no visible
progress. All three traced to one bug:

- [x] **The coordinate a drop used and the coordinate a tile actually rendered at could disagree.**
  Empty "+" slot coordinates (and `computeCellForButton()`'s fallback for an unpinned button, added
  in the prior follow-up) were both approximated as a running width×height offset assuming buttons
  pack with no gaps — while the browser rendered any *unpinned* button via CSS
  `grid-auto-flow: dense` independently. Those two only ever agreed when nothing in the tab had an
  explicit `grid_col`/`grid_row` yet. The moment one button was pinned (which every drag-to-a-cell
  action does), it left a real gap the offset arithmetic didn't know about, so a "+"-slot's computed
  coordinate could point at a cell some other button already explicitly occupied — a real, in-the-
  database overlap, not just a rendering artifact, matching the observed "tile on top of the group."
  Recorded video showed a product tile's PATCH `/place` call landing at a coordinate that then
  rendered directly under an already-pinned folder tile, visually erasing it (still present, just
  painted underneath — confirmed by dragging the covering tile away and seeing the folder reappear).
- [x] Replaced both the CSS auto-flow rendering path and the ad hoc offset math with one
  deterministic packer, `computeGridLayout()`: pinned buttons keep their explicit cell; every other
  button and every empty "+" slot are assigned row-major, first-available-gap, computed once per
  render and shared by everything that needs a coordinate — the tile's own `gridColumn`/`gridRow`
  style, the "+" slot's `data-drop` coordinate, and `swapOntoButton()`'s before/after cell lookup all
  now read from the same `gridLayout.positions`/`gridLayout.emptyCells`, so what's drawn on screen
  and what a drop targets can no longer diverge. `computeCellForButton()` is gone; nothing computes
  its own coordinate anymore.
- [x] **No option to delete a tab** — `DELETE /menu-layouts/{id}/tabs/{tab_id}` (cascade-deletes
  nested tabs and their buttons) has existed since Stage 23; the portal never wired it to anything.
  Added a `deleteTab` mutation and a hover "×" per tab in the rail (confirm dialog, since it cascades
  buttons and nested tabs) — `effectiveTabId`'s existing "fall back to the first remaining top-level
  tab" logic already covers deleting the currently-open tab correctly, no other UI change needed.
- [x] Tests: portal typecheck (`tsc -p tsconfig.app.json --noEmit`) and ESLint clean on the changed
  file. Not covered: no browser-driven re-verification of the fixed drag gestures was performed this
  session (the bug was diagnosed from a user-supplied screen recording, not reproduced live).

---

### Efficiency hardening round (post-latency-optimization) ✅

Follow-up sweep from a codebase efficiency review; five deliverables:

- [x] **Complete list fetching (the 200-row cap)** — every portal list page fetched at most one
  bounded request (`{ limit: 200 }`, categories 500), so row 201 silently never appeared; several
  pages (`/access-grants`, `/sites` pickers, `/menu-layouts`, `/reports/daily-sales`) rode the
  backend's *default* `limit=50` and truncated even sooner. New `fetchAll<T>()` helper in
  `src/api/axios.ts` pages through `skip`/`limit` until a short page arrives; all catalog/admin
  list fetches now use it (~30 call sites, 18 pages). Backend list-route caps raised
  `le=200/500 → le=1000` (28 routes) so almost every brand still costs one request. Client-side
  filtering (per the established portal pattern) is now correct at any size.
- [x] **Invoices got true server-side pagination instead** — invoice volume grows without bound, so
  `InvoicesPage.tsx` now pages at 50/request (Prev/Next controls, `Showing X–Y` range chip,
  filter changes snap back to page 1, `placeholderData` keeps rows visible while the next page
  loads). The XLSX export still covers the full filtered set (pagination params stripped).
- [x] **Log volume ~⅓ per request in production** — uvicorn `--no-access-log` (its access line
  duplicated the structured `request.completed`), `request.started` and `audit.queued` demoted to
  DEBUG (the completed line and the `audit_logs` row itself carry all the same information).
- [x] **Event-loop protection round 2** — `resend.Emails.send` (synchronous HTTP) now runs via
  `asyncio.to_thread` in all three senders (`app/utils/email.py`), so a slow Resend API can no
  longer stall every in-flight request; new `verify_password_async()` moves argon2 verification
  (~50–100 ms CPU) off the event loop on all 9 login/PIN/password-change verification call sites
  (rare admin-time *hashing* deliberately stays sync — documented in the wrapper's docstring).
- [x] **Rate limiter memory leak fixed** — `app/utils/rate_limit.py` kept one dict entry per key
  ever attempted, forever; a periodic sweep (every 1024 checks) now evicts buckets whose newest
  attempt has aged out of the largest window ever requested. Two new unit tests cover eviction
  and survival inside the window.

---

### Menu Studio — POS Layout tile style redesign ✅

Restyled the grid editor's product/folder tiles to match a reference POS mockup showing large
colour-blocked buttons (bold white product name top-left, price bottom-left, a small round "+"
quick-add badge top-right, generous rounded corners), one tile shown with a product photo filling
the tile instead of a flat colour. The rail of top-level tabs on the left was initially left
unchanged in this pass, on a since-corrected reading of the request — see the follow-up below,
which restyles the rail too.

- [x] `MenuBuilderPage.tsx` grid tiles: `rounded-xl` → `rounded-2xl`, bumped padding, bolder/larger
  product name (`font-semibold` → `font-bold`, 13.5px → 14.5px), price switched from
  `font-mono`/11.5px to a bolder 13px sans figure to read as a POS price tag rather than a table
  numeral, and a decorative round "+" badge (top-right, `rgba(255,255,255,0.28)` fill) on every
  unselected product tile — mirrors the mockup's per-tile add affordance; hidden when a tile is
  selected so it doesn't collide with the existing checkmark badge. Folder tiles keep their
  existing neutral (non-colour-filled) look, just with the same corner radius for visual
  consistency with product tiles in the same grid.
- [x] **Photo tiles**: `MenuButtonOut` gained `product_photo_url` (resolved from the linked
  product's existing `photo_url` column — no migration needed, the field and its upload
  route/service have existed since Stage 8/24, just not yet surfaced anywhere in the portal). When
  set, the tile renders the photo as a full-bleed background (its own `rounded-2xl overflow-hidden`
  wrapper, separate from the tile's own edges, so the drag-reorder insertion bars' `-7px` offset
  isn't clipped) under a bottom-weighted dark gradient scrim, with a text-shadow on the name/price
  so both stay legible over an arbitrary photo. Falls back to the flat colour tile when the linked
  product has no photo — most products still will, since there's no photo-upload control on
  `ProductsPage.tsx` yet (existing gap, out of scope here). The inspector's single-button preview
  card got the same treatment for consistency.
- [x] Verified via a static Tailwind-class-accurate mockup screenshot (rendered with the
  pre-installed Playwright/Chromium) reproducing the flat-colour, photo, selected, and folder tile
  states side by side — this environment has no reachable Postgres instance to run the full
  app/backend against real catalog data, so this was a layout/contrast check of the exact classes
  landed in `MenuBuilderPage.tsx`, not an end-to-end browser session against the live editor.

---

### Menu Studio — POS Layout tab rail style redesign ✅

Follow-up to the tile redesign above: the user clarified that leaving the rail unstyled was a
misreading — the reference mockup's lack of a nested "tab inside a tab" example was a note about
what the screenshot doesn't show, not an instruction to leave the rail alone. Restyled the rail of
top-level tabs to match the mockup's category sidebar: solid colour-blocked rows instead of a
small colour dot on a neutral list.

- [x] Each rail tab (`MenuBuilderPage.tsx`) now renders as a solid `tab.color`-filled block
  (bold name, button count, up from a `w-2.5 h-2.5` dot + `bg-brand-50` highlight on a neutral
  row). The active tab gets a `ring-[3px]` dark/light border (adapting the reference's
  black-outlined "Coffee" tab to the portal's light/dark themes) instead of the previous
  brand-tinted background; a drag-over target gets a white ring instead, so the two states stay
  visually distinct against an arbitrary tab colour. Text/icon colour on each row is resolved via
  the existing `textColorOn()` helper, same as button tiles. (Corner radius/spacing corrected in
  the follow-up below to actually match the reference — see there.)
- [x] **New tabs get a colour automatically** — `addTab`'s payload gained `color`, cycling through
  `MENU_STUDIO_PALETTE` by the rail's current tab count (mirrors how a new layout already defaults
  its own colour), so a freshly-added tab is never an unstyled fallback grey. A new
  `updateTabColor` mutation (`PATCH .../tabs/{tabId}`, a field the schema already accepted —
  `MenuTabUpdate.color` — just not exposed anywhere in the portal yet) backs a `ColorSwatchPicker`
  on each rail row so the auto-assigned colour can be changed afterward, the same picker component
  already used for layouts/buttons/categories.
- [x] Verified via the same static class-accurate mockup technique as the tile redesign (six
  differently-coloured tabs, one active with the black ring, rendered alongside product tiles) —
  same no-reachable-Postgres constraint as before, so this was a layout/contrast check, not a
  live-editor session.

---

### Menu Studio — POS Layout tab rail testing fixes ✅

Three issues from actually exercising the tab rail redesign against a live layout:

- [x] **Colour popover clipped by the rail.** `ColorSwatchPicker` (shared by Categories, button
  recolouring, and now the tab rail) rendered its popover as a plain `position: absolute` child of
  the trigger button — invisible past the edge of any scrollable/narrow ancestor, which the rail
  (`w-52`, `overflow-auto`) is exactly narrow and scrollable enough to trigger. Fixed at the
  component level (not just for the rail) by portaling the popover into `document.body` via
  `createPortal`, positioned with `position: fixed` from the trigger button's own
  `getBoundingClientRect()` (flipped left if it would overflow the right edge of the viewport,
  closed on scroll since its position isn't re-measured live) — it now always renders on top of
  everything, regardless of which ancestor is clipping/scrolling.
- [x] **Selected-swatch border blended into the swatch itself.** The 2px "you're here" border used
  `border-gray-900`/`border-gray-100`, which is nearly invisible against an already-dark or
  already-light palette colour. Replaced with a small white circular checkmark badge overlaid on
  the corner of the selected swatch — legible against every palette colour, not just lighter ones.
- [x] **Rail didn't match the reference's flush, edge-to-edge blocks.** The rail previously kept
  the container's own padding, a `gap-2` between rows, and `rounded-xl`/`shadow-sm` per tab — a
  list of separated rounded cards, not the reference's stacked, touching, square-cornered blocks
  filling the sidebar's full width. Removed the rail's own padding/gap (`p-3 flex flex-col gap-2` →
  bare `flex flex-col`, with padding reapplied only to the "Tabs" label, "+ Add tab" button, and
  help text individually) and each tab row's `rounded-xl`/`shadow-sm`, and switched the active/
  drag-over ring to `ring-inset` so it draws inward instead of bleeding into the now-touching
  neighbour above/below. The outer editor panel's own `rounded-xl overflow-hidden` still clips the
  rail's top/bottom-left corners, so only the individual rows are square — matching the reference,
  where only the overall sidebar (not each tile) has any rounding.
- [x] Verified via the same static mockup-screenshot technique as the two prior rounds (rail tabs
  now flush with no gaps, colour popover rendered fully outside the narrow rail column with a
  visible checkmark on a dark-on-dark swatch) — same no-reachable-Postgres constraint as before.

---

### Standalone auth pages — dark theme consolidation + theme toggle ✅

User-reported: the login page's dark theme didn't match the logged-in app's. Root cause —
`LoginPage.tsx`, `ForgotPasswordPage.tsx`, and `ResetPasswordPage.tsx` don't render inside
`Layout.tsx` (no session yet, so no sidebar), and each independently hard-coded its own full-screen
`bg-gray-50 dark:bg-gray-900` — a plain Tailwind grey, not `--zr-bg`, the warm cream/near-black
canvas every authenticated page actually sits on via `Layout.tsx`'s `<main>`. The wordmark
(`text-brand-800`) also had no dark-mode colour at all, reading as illegibly dark-on-dark once the
card itself went dark. Three separate copies of the same page shell meant this had already drifted
once and could easily drift again.

- [x] New `AuthPageShell.tsx` consolidates all three pages onto one shell: the
  `bg-[var(--zr-bg)]` full-screen canvas (now identical to every authenticated page's background in
  both themes), the `bg-white dark:bg-gray-800` card (kept — same convention `Modal.tsx` and every
  other card in the app already use, so this deliberately does *not* switch to the `--zr-surface`
  token, which would make the auth pages' cards look different from every other card instead of
  matching them), and the wordmark recoloured to `text-[var(--zr-accent-text)]` (the design guide's
  token for accent-toned text on a normal, non-solid-accent surface — legible in both themes, unlike
  the old hard-coded brand-800). `LoginPage.tsx` (all three of its views — the main form, the
  identity selector, and the grant selector), `ForgotPasswordPage.tsx`, and `ResetPasswordPage.tsx`
  now just supply their own form/heading content as `<AuthPageShell>` children.
- [x] **Theme toggle added** — none of these three pages render inside the sidebar, the toggle's
  only previous home, so a user landing on `/login` (or arriving fresh via a password-reset email
  link) had no way to switch themes before authenticating. `AuthPageShell` renders the same
  `useTheme()`/`☀`/`☾` toggle pattern as `Layout.tsx`'s sidebar footer, pinned to the card's
  top-right corner.
- [x] Verified visually via `vite build` + `vite preview` (this environment has no reachable
  Postgres, but these three pages render fully client-side with no API calls until form submit) and
  Playwright screenshots of `/login`, `/forgot-password`, and `/reset-password` in both themes —
  confirmed the same warm canvas colour as the rest of the app and a legible wordmark in dark mode.

---

### Menus tab removal (redundant with Menu Studio's POS Layout) ✅

User-reported: the standalone "Menus" nav tab (`MenusPage.tsx`, `/management/menus`) looked
redundant against Menu Studio. Investigation confirmed it: the `menus` table/router/service
(migration `0041`) was a saved, schedulable configuration distinct from a `menu_layouts` row, but
nothing ever consumed it — the POS read contract (`GET /pos/menu-layout`) only ever reads
`menu_layouts`, never `menus`, and Phase 2 (migration `0042`) had already added the identical
draft/schedule/publish lifecycle directly onto `menu_layouts` (`is_published`, `published_at`,
`scheduled_publish_at`), which Menu Studio's POS Layout editor already exposes. Nothing in Menu
Studio (`MenuBuilderPage.tsx`, `menu_builder_service.py`, `menu_layouts.py`) imported or depended on
the `menus` entity — only `MenusPage.tsx` itself did.

- [x] Removed: `routes/menus.py`, `services/menu_service.py`, `schemas/menu.py`, `models/menu.py`,
  `tests/integration/test_menu_routes.py`; the six `MENU_*` audit action constants; the `menus`
  page key from `PAGE_CATALOG` (`app/constants/pages.py`) and the pro-tier license gate
  (`app/constants/license_plans.py`) — see updated `ROLE_MODEL.md` §6 (19 pages, down from 20).
- [x] Migration `0048` drops the `menus` table and `menus_ref_seq` sequence (reversible downgrade
  recreates both, matching migration `0041`'s original definition).
- [x] Portal: deleted `MenusPage.tsx`; removed its route (`/management/menus`) and nav entry
  (`MGMT_NAV` in `Layout.tsx`) and the `Menu` TypeScript interface (`types/index.ts`).

---

### Menu Studio — tab rail colour trigger follow-up ✅

User feedback on the tab rail redesign's own colour-swatch trigger: a small square filled with the
tab's own colour, sitting on a tile already filled with that same colour, read as an odd redundant
chip rather than a useful preview (unlike `ColorSwatchPicker`'s other use on `CategoriesPage.tsx`,
where the swatch sits on a neutral card row and a colour preview makes sense there).

- [x] `ColorSwatchPicker` gained a `trigger?: 'swatch' | 'icon'` prop (default `'swatch'`, so
  `CategoriesPage.tsx`'s usage is unchanged). `trigger="icon"` renders a small edit-pencil glyph
  instead of a `value`-filled square — used only by the tab rail's colour picker, since that's the
  one trigger that sits on a surface already filled with its own `value`.
- [x] **Immediate follow-up** — the first pass rendered the pencil in an opaque white rounded
  badge (`bg-white/90 shadow-sm`), which the user flagged as still not matching the reference: they
  wanted it to read as a plain glyph with no background of its own, at the same small scale as the
  adjacent delete "×" button. Changed to `w-5 h-5 rounded hover:bg-black/15` with no background/
  text-colour classes at all, so it inherits `color` from the tab row's own `style={{ color: tabFg
  }}` via normal CSS cascade — identical sizing and "just a hover highlight" styling to the delete
  button beside it, rather than a separate opaque chip.
- [x] Verified via the same static mockup-screenshot technique as the prior rail rounds.

---

### SuperAdmin/User table merge ✅

User request: condense the separate `superadmins` table/portal-page into a role on `User`, and
condense the SuperAdmins/Users admin-portal pages into one page.

**Deliverables:**
- [x] Migration `0050`: `users.superadmin_role` (nullable, `admin`|`reseller_staff`); `users.group_id`
  made nullable (pure admin-portal rows have no tenant scope); existing `superadmins` rows migrated
  into `users` as new rows preserving `id` (so `groups.created_by_id` keeps resolving) and their
  historical `PTL-xxxxxx` ref string; `groups.created_by_id` FK re-pointed from `superadmins.id` to
  `users.id`; `superadmins` table + `superadmins_ref_seq` dropped. Full `downgrade()` provided
  (recreates `superadmins`, copies `superadmin_role` rows back out, restores `group_id NOT NULL`).
- [x] `app/models/superadmin.py` deleted; `app/models/user.py` gained the `superadmin_role` column.
- [x] `app/utils/dependencies.py`: `get_current_superadmin()`/`require_super_admin()` now query `users`
  filtered by `superadmin_role IS NOT NULL` instead of a separate `superadmins` table;
  `CatalogAccess.portal_access` is now `User | None`.
- [x] Service layer: ~20 files mechanically collapsed `SuperAdmin`/`User | SuperAdmin` actor types to
  plain `User` (`access_grant_service.py`, `access_profile_service.py`, `menu_builder_service.py`,
  `tax_template_service.py`, catalog services, etc.); `group_service.py`/`brand_service.py`/
  `site_service.py`'s Reseller Staff "own accounts only" scoping now reads `actor.superadmin_role`
  instead of a separate `SuperAdmin.role`; `access_grant_service.create_grant()`'s `granted_by_id` is
  now always attributable (previously NULL for a portal-admin actor, since `SuperAdmin` wasn't itself a
  `users.id` row).
  - `user_service.find_email_owner()` simplified to one `users` query (was: check `SuperAdmin` then
    `User`).
  - `portal_auth_service.py`: dead `login()` deleted (no route called it — only `refresh()` was
    wired); `reset_password()` collapsed from a two-table check to one `users` lookup by
    `password_reset_token`.
  - `management_auth_service.py` (the core rewrite): `_load_superadmin()`/`_load_users()` replaced by
    one `_load_users_by_email()` + `_authenticate_candidates()` helper shared by `login()` and
    `issue_identity_token()`, splitting every matching row's verified credentials into
    superadmin-capable / grant-capable buckets. The `available_identities`/`identity-token` wire
    contract is unchanged — a hybrid row (both capabilities on one row) or several rows sharing an
    email both flatten into the same response shape the old two-table design used, so the portal's
    disambiguation UI needed no changes.
- [x] Routes: `routes/superadmins.py` deleted; its list/get/create/update/suspend/activate endpoints
  folded into `routes/users.py` (`GET /users/{id}` added — previously only sub-resource GETs existed;
  `POST /users/{id}/reactivate` added for suspend/activate parity; `superadmin_role` added to
  create/update payloads and list filters, gated by a new `_require_admin_role()` check — a Reseller
  Staff portal admin can manage tenant Users freely but cannot create/promote other portal admins).
  `routes/users.py`'s previously-inline schemas (`UserOut`, `UserCreate`, etc.) moved into
  `schemas/user.py` alongside the former `schemas/superadmin.py` contents, per the project's
  schemas-live-in-schemas convention. The `_PASSWORD_SET_ALLOWED_EMAIL` single-trial-account gate on
  admin-set passwords was removed — any portal admin may now set another user's password. 9 other
  route files (`brands.py`, `groups.py`, `sites.py`, `licenses.py`, `license_invoices.py`,
  `email_templates.py`, `admin_tax_templates.py`, `pos_devices.py`, `admin_impersonation.py`,
  `reference_data.py`) mechanically switched their `Depends(require_super_admin)`/
  `Depends(get_current_superadmin)` type hints from `SuperAdmin` to `User`.
- [x] `app/cli.py`'s `bootstrap-super-admin` now creates a `users` row (`group_id`/`brand_id` NULL,
  `superadmin_role='admin'`) instead of a `superadmins` row.
- [x] `app/constants/audit_actions.py`: added `USER_REACTIVATED`, `USER_SUPERADMIN_ROLE_UPDATED`;
  removed the now-unused `PORTAL_USER_CREATED`/`UPDATED`/`SUSPENDED`/`ACTIVATED` (the CLI bootstrap
  command's create action moved to the existing `USER_CREATED`).
- [x] Portal: `SuperAdminsPage.tsx` deleted; `pages/UsersPage.tsx` (the SuperAdmin-portal-only one)
  rewritten as the merged page — same route (`/users`), row-per-user with the existing embedded grant
  editor, plus a new "Portal Role" column/badge and filter, a "Portal Role" select in the create/edit
  modals (Admin/Reseller/none, editable only by an Admin-role portal admin), and adoption of the shared
  `FilterBar` component (replacing both former pages' hand-rolled filter bars). `Layout.tsx`'s
  `SUPER_ADMIN_ONLY_NAV` collapsed from two entries ("SuperAdmins", "Users") to one ("Users");
  `App.tsx`'s `/superadmins` route removed. `types/index.ts`'s separate `SuperAdmin` interface and
  the barely-used minimal `User` interface were merged into one exported `User` type matching the
  backend's `UserOut` (fixing the pre-existing drift where the real shape lived in a page-local
  `AppUser` type instead); `AuthContext.tsx`'s `isSuperAdmin()` now checks `superadmin_role` instead of
  a `role` field, and its session-restore fetch moved from the deleted `GET /portal-users/{id}` to the
  new `GET /users/{id}`. `LoginPage.tsx`/`AuthContext.tsx`'s identity/grant selector views needed no
  changes — the wire contract they consume was kept stable by design.
  `pages/management/UsersPage.tsx` (brand-scoped delegated grant management) is unchanged and still
  has no Admin/Reseller option.
- [x] Tests: `test_superadmins_routes.py` deleted, its create/list/get/update/suspend+reactivate
  coverage folded into `test_users_routes.py` alongside new `superadmin_role`-specific cases (Admin-
  only grant/change, email+password prerequisite, invalid role value, self-deactivate guard).
  `conftest.py`'s `test_superadmin` fixture now builds a `User(group_id=None, superadmin_role="admin")`
  row instead of a `SuperAdmin` row (fixture name kept — `portal_auth_headers` and every existing test
  already depend on it). `test_portal_auth_routes.py`/`test_management_auth_routes.py`'s "shared email"
  disambiguation tests updated to construct a second `User` row instead of a `SuperAdmin` row, plus new
  cases for the previously-impossible single-row hybrid scenario (one row with both `superadmin_role`
  and a portal-capable grant). `test_access_grants.py`/`test_email_template_routes.py`/
  `test_user_password_reset.py` updated their local portal-admin fixtures/helpers to the same pattern.
- [x] Docs: `ROLE_MODEL.md` §1/§3 rewritten to describe the merged model as implemented (superseding
  the Stage-15 separate-table design); `ARCHITECTURE_MAP.md`'s Identity/Terminology/routes-inventory/
  Auth sections and `DATA_MODEL.md`'s stale `portal_users`/`pos_users` section updated to match;
  `CLAUDE.md` gained this stage's changelog entry.

**Known limitations:** no reachable Postgres in this environment to run the integration test suite or
exercise the merged portal page end-to-end in a browser — verified instead via `python -m py_compile`
across the whole backend+tests tree, an actual `from app.main import app` import (confirms no
ImportError/circular-import regressions), `alembic heads` (confirms a single valid migration head),
`pytest --collect-only` (791 tests collect with no fixture/import errors), and the portal's `tsc --noEmit`
+ `npm run build` (both clean). See a future session for a live-DB pass if one becomes available.

---

### Users edit page — "POS - Site Assignment" toggle ✅

User request: expose `users.is_pos_multi_site_enabled` (already on the model and consumed by
`pos_auth_service.login()` since it gates the POS site-selector prompt) on the admin portal's Users
edit page — it had a column and login-time behaviour but no read/write path anywhere in the API or
portal.

**Deliverables:**
- [x] `schemas/user.py`: `UserOut` gained `is_pos_multi_site_enabled: bool = False`; `UserUpdate`
  gained `is_pos_multi_site_enabled: bool | None = None` (optional — the existing
  `model_fields_set` sentinel pattern already used for `backend_role`/`superadmin_role`
  distinguishes "not supplied" from an explicit value).
- [x] `routes/users.py`: `_attach_sites()` and `create_user()`'s response now populate the field;
  `update_user()` applies it only when the key is present in the request body, and its `USER_UPDATED`
  audit row's `after_state` now includes the new value (no new audit action — this folds into the
  existing generic user-edit audit like the name/email fields do).
- [x] `types/index.ts`'s `User` interface gained `is_pos_multi_site_enabled: boolean`.
- [x] `pages/UsersPage.tsx`: the edit modal's "User Details" section gained a "POS - Site Assignment"
  checkbox (with the same behaviour description as the model's docstring) between the Portal Role
  select and the password field; `editMutation` now always sends the current toggle state alongside
  the other fields.
- [x] Tests: `test_users_routes.py` gained `test_update_user_pos_multi_site_enabled_toggle_writes_audit`
  and `test_update_user_omits_pos_multi_site_enabled_leaves_unchanged`.

**Known limitations:** no reachable Postgres in this environment — verified via `ast.parse` on the
touched Python files and the portal's `tsc --noEmit` (clean). The new tests were not executed against
a live database; a future session with Postgres available should run them.

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

**Full narrative, architecture decisions, and per-slice detail live in `ANDROID_POS_BUILD_PLAN.md`** —
this section is a condensed checklist kept in sync with it, not a duplicate of it. Read the build plan
first when picking this phase back up.

### Stage 25 — Android Auth & Catalog 🚧

**Deliverables:**
- [x] Android project initialised: Kotlin + Jetpack Compose + Hilt + Retrofit + Room
- [x] Project structure: `data/`, `di/`, `ui/screens/`, `ui/components/`, `ui/viewmodel/`, `ui/theme/`
- [x] Screen scaffolding exists for: `auth/`, `cart/`, `catalog/`, `payment/`, `switchuser/`
- [x] `PosNavHost.kt` navigation graph
- [x] Backend: Migration `0011` adds access grants table extensions for management access
- [x] POS login screen (email + password) — functionally wired, not yet styled to the design bundle
- [x] PIN entry — folded into `SwitchUserScreen` (email + PIN) rather than a separate screen
- [x] Site selector screen (for users with multi-site access)
- [x] Self-service license-seat device claiming (migration `0051`, PR #110) — replaced the
      admin-pre-registration + Device Setup screen flow this stage originally shipped with. A terminal
      now claims (or re-pairs) a license seat automatically on login instead of requiring a portal
      admin to issue a `device_token` first. `DeviceSetupScreen.kt`/`DeviceViewModel.kt` are deleted.
      See `ANDROID_POS_BUILD_PLAN.md`'s "What the self-service license-seat auth rework shipped" for
      full backend/portal/Android detail.
- [x] Register (order-entry) screen — `OrderEntryScreen.kt`, exact match to
      `design_handoff_zedread/ZedRead Register.dc.html`'s header/category-rail/product-grid/order-pane
      layout, replacing the earlier generic `CatalogScreen`/`CartScreen` pair (the design has no
      separate cart screen). Qty stepper backed by new `PATCH`/`DELETE .../line-items/{id}` routes.
      Modifier customise sheet and Payment flow exact-match styling are still pending — see
      `ANDROID_POS_BUILD_PLAN.md`.
- [x] Retrofit API client wired to backend endpoints
- [ ] Room local cache for catalog (offline-capable browsing) — Phase 2 of the build plan
- [x] Hilt DI modules for network, database, repositories

### Stage 26 — Android Payments & Printing 🔜

**Deliverables:**
- [x] Payment screen (cash / card / split) — functional, generic UI; no Voucher tab yet, exact-match
      styling still pending
- [ ] Docket/receipt printing (`printing/` module scaffolded)
- [x] Switch user flow (PIN re-entry without full logout)
- [x] End-of-day cash-up screen (`CashUpScreen.kt`) — closes the register session, shows the
      computed Expected/Counted/Variance summary, logs the operator out. Entry point is a "Cash up"
      icon on `CatalogScreen`'s top bar for now (no account/nav menu exists yet — that's
      design-bundle-dependent, see `ANDROID_POS_BUILD_PLAN.md`).
- [ ] Invoice history screen
- [ ] Error handling + offline sync reconciliation
- [ ] APK build + signing configuration — CI produces an unsigned debug APK; release signing not set up

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
