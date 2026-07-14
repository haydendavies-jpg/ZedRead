# ZedRead — Ground-Truth Functional Map

Generated from reading actual code (routes/models/services/configs), not from written summaries or docs.
Use this to orient quickly in new sessions. If a written summary (docx, README) contradicts this, the
code is the source of truth — flag the discrepancy.

## What it is

Multi-tenant POS: super-admins manage org hierarchy via a React portal; staff run sales on Android
terminals; one FastAPI backend + one Postgres DB is the sole source of truth for both clients.

```
Group ──┬── Brand ──┬── Site (physical location, one Android terminal each)
         │            ├── Products / Categories / Modifiers / Combos / Tax rules
         │            └── POS Users (staff, scoped to a brand, granted access to sites)
         └── Licenses (per-site subscription/billing)
```

Transaction flow: Invoice → line items (each product stores a tax-INCLUSIVE price and a derived
tax-EXCLUSIVE price; is_taxable picks which is charged — taxable → inclusive with GST embedded,
not taxable → exclusive; no rate math at sale) → modifiers → discount → tax breakdown
→ payment → paid/voided/refunded. Refunds are a new Invoice linked via `refund_of_id`, not a mutation.

## Deployment topology

- **pos-backend**: Railway, Dockerfile, FastAPI/uvicorn on :8000, owns Postgres, health check `/health`.
- **pos-portal**: Railway, nixpacks, static SPA built with `npm run build`, served via `npx serve dist -s`.
  **Zero server-side code** — pure REST client over `src/api/axios.ts`, CORS-allowed via `PORTAL_ORIGIN`.
- **pos-android**: native Kotlin/Compose, talks directly to the same backend API (Retrofit), offline-capable
  catalog cache, syncs invoices when online.
- **Redis**: only used as the **Celery broker + result backend** (`app/celery_app.py`). The sole job riding
  on it is `expire_overdue_licenses` (`app/tasks/license_tasks.py`), daily at 02:00 UTC. No caching, no
  sessions, no rate-limiting, no pub/sub anywhere in the codebase.
- One shared Postgres instance; backend is the sole writer; portal/Android are read/write REST clients only
  through backend endpoints (no direct DB access).

## Auth (stateless JWT, no server sessions)

1. **Portal Access JWT** (`type=access`) — SuperAdmin. Issued by `portal_auth_service`.
2. **Management JWT** (`type=mgmt_access`) — User with a `backend_role` on an active grant; issued
   after a scope-selection step (`/auth/portal/management-token`) when the user has multiple grants.
   Admin impersonation (`POST /admin/impersonate`) issues the same token type with `imp_*` claims
   so audit rows attribute to the admin.
3. **POS Access JWT** (`type=pos_access`) — terminal-scoped (single site); PIN verification returns
   a fresh token for quick user-switching without full logout.

Tokens stored in localStorage (portal; impersonation tokens per-tab in sessionStorage) or DataStore
(Android). Login and PIN-verify are rate-limited per account (in-process sliding window,
`app/utils/rate_limit.py`; configurable via `LOGIN_RATE_LIMIT`/`PIN_RATE_LIMIT`, disable with
`RATE_LIMIT_ENABLED=false`). All token types are now revocable server-side:
- **POS** access tokens carry a `jti` matched to an active `user_pos_sessions` row;
  `resolve_access`/`resolve_catalog_access` reject a token whose session has ended, and
  `POST /auth/pos/logout` ends the session.
- **Portal and management** tokens carry a `tv` (token_version) claim matched to
  `superadmins.token_version` / `users.token_version`; a mismatch is rejected. The counter is bumped
  by password change, password reset, and `POST /auth/portal/logout` (logout-everywhere), invalidating
  all outstanding tokens for that identity.

## Routes inventory (pos-backend/app/routes)

| File | Endpoints |
|---|---|
| portal_auth.py | login, refresh, management-token, mgmt-refresh, change-password |
| pos_auth.py | login, pin/set, pin/verify |
| brands.py / groups.py / sites.py | CRUD + suspend/activate, paginated list/filter |
| products.py | CRUD, soft-delete, photo upload (Supabase Storage), bulk XLSX export/template/import (Stage 19) |
| categories.py | list/create/update (system categories protected), bulk XLSX export/template/import (Stage 19) |
| invoices.py | create, line-items, modifiers, discount, pay, void, refund |
| tax.py | brand tax category CRUD (taxability classes only — rates come from admin templates) |
| admin_tax_templates.py | SuperAdmin-only jurisdiction tax templates + rates; invoice engine resolves site rates from these |
| licenses.py | CRUD, disable/enable |
| users.py / superadmins.py | CRUD, suspend/activate, PIN admin set, grants |
| access_grants.py (+ profiles_router) | grant CRUD, permission tiers, page permissions |
| admin_impersonation.py | SuperAdmin "session into" an entity's master-user grant |
| email_templates.py / reference_data.py | admin-editable email templates; countries/timezones/tax-id labels |
| reports.py | daily-sales, product-revenue, payment-methods, tax-collected |
| modifiers.py / combos.py / variants.py | catalog extras management; combos.py/variants.py each also expose a brand-wide `list_router` (`GET /combos`, `GET /variants`, joined to parent product) plus bulk XLSX export/template/import (Stage 22). modifiers.py also covers Menu Studio "comboing": `GET /modifier-groups/detailed` (nested groups→options→linked groups), `POST/DELETE /modifier-options/{id}/links[/{group_id}]`, group/option soft-delete, group duplicate |
| reporting_groups.py | Reporting Group CRUD (Stage 16), bulk XLSX export/template/import (Stage 19) |
| menu_layouts.py | POS Menu Builder (Stage 23; grid editor Phase 2): layout/tab/button CRUD, reorder, publish/unpublish, duplicate, schedule/cancel-schedule-publish, button bulk-recolor/bulk-delete/group-into-tab (management JWT); `pos_router` exposes `GET /pos/menu-layout?site_id=`, the read contract for Android |
| menus.py | Menus (Menu Studio redesign) — distinct from a `menu_layouts` layout: CRUD, duplicate, schedule/cancel-schedule/publish (management/portal JWT only) |
| pos_devices.py | terminal device registration |
| user_invites.py / license_invoices.py | onboarding invites, recurring license billing |

## Models inventory (pos-backend/app/models)

Hierarchy: `groups` ← `brands` (group_id) ← `sites` (brand_id).
Catalog: `categories` (carries `default_color`, the POS button colour its products default to —
Menu Studio redesign), `products` (base_price_cents BIGINT), `product_variants`, `product_combo_groups/options`,
`modifier_groups/options`, `product_modifier_group_links` (M:N), `modifier_option_group_links`
(M:N, self-referential through `modifier_groups` — an option "comboing" into another group, Menu
Studio redesign), `reporting_groups` (Stage 16, one level above Category), `menus` (Menu Studio
redesign — a saved, schedulable configuration distinct from a `menu_layouts` row, with an optional
`menu_layout_id` FK and the same brand/site `scope` pattern). `product_variants` and `product_combo_groups` each carry a `ref`
(`VAR-000001` / `CMB-000001`) and nullable `display_name` (Stage 22) — there is no separate `Combo`
table; a "combo product" is a `Product` that owns `product_combo_groups` rows, so
`ProductComboGroup` is the entity the Stage 22 portal page surfaces as "Combo". Products carry `base_price_cents`
(tax-inclusive), `price_ex_cents` (derived), `is_taxable`, `ref` (human-readable PRD-000001 code,
wired into the ORM/schema in Stage 24 — previously dormant since migration `0013`), `print_name`
(nullable, falls back to `name`), and `is_open_item` (flexible price/name at sale time, gated by the
`can_use_open_item` capability + optional `open_item_max_price_cents` ceiling on `AccessProfile`).
Categories' own `ref` (CAT-000001) was likewise dormant since migration `0013` and was wired into
the ORM/schema in Stage 19, joining the already-wired `products.ref` and `reporting_groups.ref`
(RPG-000001) as the matching key for the Stage 19 bulk XLSX import/export (`export_service.py` /
`import_service.py`, shared across all three entities).
`tax_templates`/`tax_template_rates`
(admin-owned, jurisdiction-scoped country→state→county→city) supply the country rate used to derive
a product's exclusive price at save time. `tax_categories`/`tax_rates` are legacy (retained, not used
for invoice tax).
Identity: `users` (brand- or group-scoped staff), `superadmins` (portal admin, no scope),
`user_access_grants` (site|brand|group scope + access_profile_id + backend_role + is_default),
`access_profiles` (permission tiers, JSON perms), `access_profile_page_permissions`, `user_pins`.
Transactions: `invoices`, `invoice_line_items` (snapshotted name/price), `invoice_line_modifiers`,
`invoice_tax_breakdowns`, `payments`.
Billing: `licenses` (site_id, one per site), `license_invoices`.
Ops: `user_pos_sessions`, `pos_devices`, `audit_logs` (immutable), `user_invites`.
Menu Builder (Stage 23; grid editor Phase 2): `menu_layouts` (brand_id, nullable site_id, `scope`
'brand'|'site' with a check constraint tying the two together, `is_published`, `version`, `color`,
`published_at`, active-time/day-of-week scheduling `is_all_day`/`start_time`/`end_time`/
`active_days` — when a *published* layout is visible on the POS, distinct from `is_published` —
and `scheduled_publish_at`, the "Schedule publish" bulk action), `menu_tabs` (layout_id, ordered via
`display_order`, self-referential `parent_tab_id` for unbounded nesting, own `color`), `menu_buttons`
(tab_id, `kind` 'product'|'folder', `product_ref` — a product's `ref` code, deliberately not a FK so
a button survives the underlying product being deleted and recreated with the same code, nullable
since a folder button has none — `child_tab_id` instead, `width`/`height` 1-6×1-4 grid-cell span, no
x/y coordinates since the portal's 6-column CSS grid packs tiles via `grid-auto-flow: dense`,
optional `color` override falling back to the linked product's category default colour). More than
one layout may be `is_published` at once (per-site/day-part menus).

## Terminology

| Term | Meaning |
|---|---|
| Group | Top-level tenant, no parent |
| Brand | Business under a Group; owns catalog, staff, access profiles |
| Site | Location under a Brand; one license, one Android terminal |
| User | Staff (model `User`, table `users`); logs into terminal; granted access to sites. Renamed from "POS User" per `ROLE_MODEL.md` |
| SuperAdmin | Portal admin (model `SuperAdmin`, table `superadmins`); unrelated to Brand/Site scoping. Renamed from "Portal User" per `ROLE_MODEL.md` |
| Access Grant | Join record: user + scope (site/brand/group) + Access Profile |
| Access Profile | Named permission tier (JSON perms) belonging to a Brand |
| Management JWT | Issued to a POS user with portal access after they pick a scope/grant |
| PIN | Secondary credential for fast terminal user-switching (separate from login password) |
| Combo | Bundled choices baked into one product (`product_combo_groups/options`) |
| Modifier | Reusable add-on attachable to many products via join table |

## Known discrepancies to watch for vs written summaries / design doc

- Redis is **not** a cache/session/rate-limit layer — it's a Celery broker for one nightly job only.
- No session-based auth exists anywhere — fully stateless JWT across all three token types.
- Portal has no backend logic of its own — pure static SPA REST client.
- Live code already covers invoices/modifiers/combos/reports (Phase 3 territory per CLAUDE.md rollout
  table) — if a summary claims an earlier active stage, reconcile against actual route/model inventory above.
- The `ROLE_MODEL.md` redesign is **partially implemented**: the rename is live (models
  `SuperAdmin`/`User`, tables `superadmins`/`users`, routes `superadmins.py`/`users.py`) and
  `access_profile_page_permissions` exists, but grants still reference `access_profiles` and the
  `backend_role` enum — the full 5-role model is not complete. Verify against code before assuming
  either the old or the target model.

*Last mapped: 2026-07-10. Re-verify against code if it has changed significantly since.*
