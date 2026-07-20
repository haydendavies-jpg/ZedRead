# ZedRead POS — Project Rules

## What this project is
Android POS system with a FastAPI/PostgreSQL backend and a React super-admin portal.
Multi-tenant hierarchy: Group → Brand → Site.

## Read these first
- **ARCHITECTURE_MAP.md** — functional map of the actual codebase (routes, models, deployment,
  terminology), derived from code. Read this when picking up the project in a new session.
  If it conflicts with any other doc, the code (and this map) wins — flag the conflict.
- **ROADMAP.md** / **STAGE_STATUS.md** — phase and stage tracking; keep in sync with this file's
  rollout table whenever stages are added or completed.

`pos_master_v5.docx` is retired — it was never maintained past early stages and is no longer a
reference. Do not look for it or gate implementation on it.

## Scoped rules (auto-loaded when working in those directories)
- Backend code style, naming, FastAPI patterns: `pos-backend/app/CLAUDE.md`
- Testing rules and fixtures: `pos-backend/tests/CLAUDE.md`
- Portal (React) style, components, brand: `pos-portal/CLAUDE.md`

## Rollout plan
Built in 10 phases across 26 stages. Work within the current stage only; never implement
future-stage features unless explicitly instructed.

| Phase | Stages | Summary |
|---|---|---|
| 1 — Foundation & Portal | 1–6 | DB, auth, hierarchy, licenses, React portal, deploy |
| 2 — POS Catalog | 7–9 | POS auth, products, variants, modifiers, combos |
| 3 — Transactions | 10–12 | Invoice engine, payments, reporting, deploy |
| 4 — Identity & Permissions Redesign | 15 | Rename + 5-role model — see `ROLE_MODEL.md` |
| 5 — Catalog Foundations | 16–18 | Reporting groups, delegated user creation, permissions UI |
| 6 — Catalog Data & Table UX | 19–20 | Bulk XLSX import/export, inline edit, filters, columns |
| 7 — Invoices & Extended Catalog | 21–22 | Invoice detail/PDF/XLSX reporting + change log; Variants/Combos portal pages |
| 8 — POS Menu Builder | 23 | Graphical menu layout prototype + publish pipeline |
| 9 — Product Model Extensions | 24 | Product code, print name, open item |
| 10 — Android App | 25–26 | Kotlin + Jetpack Compose POS application |

Stage numbers 13–14 are retired (previously reserved for the Android phase, now renumbered to
25–26 to make room for Stages 16–24 ahead of it — see ROADMAP.md/STAGE_STATUS.md for the rationale).

**Stage 15 — complete:** the rename and role/permission model in `ROLE_MODEL.md` — SuperAdmin
(Admin/Reseller Staff), User (Master User/Admin/Reporting Only/Manager/Staff), required-field
rules, access_profiles replaced by the 5 roles, per-page permission grants within the 5 page
categories, license gating, cross-identity login disambiguation, and the portal frontend rename
(nav/routes/components now say SuperAdmins/Users) are all implemented. The per-category page list
(§6 of `ROLE_MODEL.md`) is resolved and implemented — do not re-open it.

**Stages 16–18 — complete.** Reporting Groups (brand-scoped, above Categories), Delegated User
Creation (scope ladder + role ceiling on grant creation/update, Master User ungrantable through
`/access-grants`), and the Permission Scopes portal UI (toggle page grants per access profile, with
a license-gate preview where a site context is available) are all implemented — see
`STAGE_STATUS.md` for details.

**Stage 19 — complete.** Shared `export_service.py`/`import_service.py` (template export with
data-validation dropdowns, full export, validate-then-upsert import) for Products, Categories, and
Reporting Groups, keyed on each entity's `ref` code with partial-update semantics (only columns
present in the uploaded header row are touched). `categories.ref` is now wired into the ORM/schema,
joining the already-wired `products.ref` (Stage 24) and `reporting_groups.ref` (Stage 16). See
`STAGE_STATUS.md` for full deliverables.

**Stage 20 — complete.** Products table gained Reporting Group + Category columns resolved via a
join (no denormalization); Products/Categories/Reporting Groups all gained a shared `FilterBar`
(category, reporting group, active state, name/code search) and click-to-edit inline cells (name,
price, category, reporting group, active-state), alongside the existing modal-based create flow.
See `STAGE_STATUS.md` for full deliverables.

**Stage 21 — complete.** New `invoice_report_service.py` (filtered list — date range, site, status,
amount range — reading `vw_invoice_detail`; full detail view with line items/modifiers/tax
breakdown/payments; change-log panel reading `audit_logs` by `entity_type='invoice'`), a read-only
`export_invoices()`/`build_invoices_export()` pair added to Stage 19's `export_service.py`, and a new
`invoice_pdf_service.py` rendering a standard single-invoice PDF via `weasyprint`. All exposed on a
new `/invoice-reports` router (`routes/invoice_reports.py`) — the transactional engine in
`routes/invoices.py` is untouched. Fixed a gap in `create_refund()`: it previously logged the refund
only against the *new* refund invoice's `entity_id`, which meant the original invoice's change log
never showed it was refunded — it now also writes a row against the original invoice's own
`entity_id`. Portal gained an `InvoicesPage` (filters + XLSX export button) and `InvoiceDetailPage`
(line items, tax breakdown, payments, change log, PDF download), reachable from the management nav
and as a new tab on the SuperAdmin's Brand detail page. See `STAGE_STATUS.md` for full deliverables.
**Stage 22 — complete.** Variants and Combos each gained a `ref` sequence (`VAR-000001` /
`CMB-000001`, migration `0039`) and a nullable `display_name` distinct from the internal/POS-facing
name. There is no separate `Combo` table — a "combo product" is just a `Product` that owns
`product_combo_groups` rows, so `ProductComboGroup` is the entity Stage 22 surfaces as "Combo";
it also gained `is_active` (soft-delete) to match `product_variants`' existing flag, plus
update/deactivate/reactivate service functions and routes it previously lacked. New brand-wide
`GET /variants` and `GET /combos` (joined to their parent product) power a combined portal page
(`VariantsCombosPage.tsx`, one sidebar entry, two tabs) with filters, inline edit, and
import/export via Stage 19's shared `export_service.py`/`import_service.py`. Variant import is
update-only (matched by `ref`) — creating a variant requires per-brand attribute assignment, which
doesn't fit a fixed spreadsheet header and has no portal UI of its own yet; Combo import supports
both create (via a `product_ref` column) and update. Products' edit modal shows its linked variants
read-only; the combined page's rows already show their linked product inline, covering "Variant
shows its linked product" without a separate variant detail page. See `STAGE_STATUS.md` for full
deliverables.

**Stage 23 — complete.** New `menu_layouts` / `menu_tabs` / `menu_buttons` tables (migration `0040`)
back a `menu_builder_service.py` and a new `/menu-layouts` router (management CRUD, tab/button
reorder, publish/unpublish) plus a `GET /pos/menu-layout?site_id=` read contract for Android to
eventually consume (Android-side consumption stays out of scope). Buttons reference products by
`ref` code (not FK), so a button survives product recreation; publishing warns rather than blocks
when a code no longer resolves to an active product. Prototype scope honoured: single-level tabs +
buttons only, no nested sub-menus. More than one layout can be published at once (e.g. per-site or
day-part menus). Portal gained `MenuBuilderPage.tsx` (layout list + a tabs/buttons builder using
native HTML5 drag-and-drop — no new dependency), reachable from the management nav and as a new tab
on the SuperAdmin's Brand detail page. Stage 24 (Product Model Extensions) was already complete
ahead of this stage — it had no blocking dependency on 22/23 — see `STAGE_STATUS.md` for its
deliverables. Do not begin Stage 25+ Android work yet.

**Menu Studio visual/functional redesign (post-Stage-23, Table view + Menus + POS Layout — complete).**
Implemented from a Claude-designed HTML mockup (`design_handoff_menu_studio/` — high-fidelity
reference, not production code). Scope was explicitly split with the user into phases: Phase 1
covered the **Table view** (Products/Modifiers/Categories) and the new **Menus** screen; Phase 2
(below) delivers the previously-deferred **POS Layout grid editor** — Stage 23's "prototype scope,
single-level tabs + buttons only" text above is superseded by Phase 2 for `menu_layouts`. Phase 1
delivered:
- **Category default colour**: `categories.default_color` (migration `0041`, hex `#RRGGBB`, default
  `#5A5550`) — the POS button colour a category's products default to; editable via a swatch+palette
  popover (`ColorSwatchPicker.tsx`) on the redesigned `CategoriesPage.tsx`, which now groups
  categories into cards by reporting group with row/group checkboxes and a floating bulk
  "assign to reporting group" bar, plus inline add-forms for new categories/reporting groups.
- **Modifier "comboing"**: a new `modifier_option_group_links` table (self-referential through
  `modifier_groups` via a `ModifierOption`) lets an option expand into another modifier group on the
  POS — the inline-nested-cascade pattern from `Modifier Comboing Options.dc.html` ("option 1", the
  one the design doc says was chosen). `GET /modifier-groups/detailed` nests groups → options → each
  option's linked groups (one level deep; the schema supports deeper nesting later without a
  migration, the API doesn't yet). New `ModifiersPage.tsx` (net-new — no prior portal page existed
  for modifier management) renders this as cards with an expand/collapse chip per linked option.
  Groups/options also gained soft-delete (`DELETE /modifier-groups/{id}`,
  `DELETE /modifier-options/{id}`) and group duplication (`POST /modifier-groups/{id}/duplicate`),
  none of which existed before.
- **Products tab**: `GET /products` now also joins each row's category colour and a comma-joined
  list of active linked modifier group names (`ProductListItem.category_color`/`modifier_names`,
  resolved via a correlated subquery — no denormalization), surfaced as a colour dot and a
  Modifiers column on `ProductsPage.tsx`. Existing inline-edit/filter machinery is unchanged.
- **Menus** (new entity, distinct from a `MenuLayout`): `menus` table (migration `0041`, `MNU-000001`
  ref sequence) with `draft`/`scheduled`/`published` status, `scheduled_at`/`published_at`,
  optional `menu_layout_id` (which POS button layout it activates), and the same brand-vs-site
  `scope`/`site_id` assignment pattern `menu_layouts` already uses (sites stand in for
  "registers/channels" — no dedicated register entity exists). `menu_service.py` +
  `routes/menus.py` (`/menus`, management/portal JWT only) support create/update/duplicate/
  schedule/cancel-schedule/publish. New top-level `MenusPage.tsx` + nav entry.
- **Theming**: portal-wide light/dark mode — `ThemeContext.tsx` toggles a `dark` class on `<html>`
  (Tailwind `@custom-variant dark`), persisted to `localStorage`, toggle in the sidebar footer. New
  Menu Studio screens are fully dark-mode-styled by hand; the ~25 pre-existing pages got a mechanical
  sweep pairing common light-mode Tailwind classes with `dark:` companions (not a pixel-perfect
  per-component pass — see `pos-portal/CLAUDE.md`). `Source Serif 4`/`IBM Plex Mono` are wired as
  Tailwind's `font-serif`/`font-mono` tokens; `Lora` (wordmark) and the portal's `system-ui` body font
  are unchanged outside Menu Studio/Menus screens, which apply `IBM Plex Sans` directly instead of a
  global font swap — see `pos-portal/CLAUDE.md`'s "flagged conflict" note for the rationale.
- Nav: `MGMT_NAV` now has "Menu Studio" (Products/Modifiers/Categories tabs + a `Table`/`POS Layout`
  segmented control, the latter delegating to `MenuBuilderPage`, rewritten by Phase 2 below) and
  "Menus"; the old standalone Products/Categories/Menu Builder nav entries are gone but their
  routes/components still exist (used directly by `BrandDetailPage`'s own tabs, and kept mounted in
  `App.tsx` for compat).

**Phase 2 — POS Layout grid editor (complete).** The graphical editor the Stage 23 prototype's
single-level tab/button list stood in for. Migration `0042` adds: `menu_layouts.color`/
`published_at`/active-time scheduling (`is_all_day`/`start_time`/`end_time`/`active_days` — when a
*published* layout is visible on the POS, e.g. Breakfast only 7am–11am, distinct from
`is_published`)/`scheduled_publish_at` (the "Schedule publish" bulk action — persisted only, same
no-Celery-job gap as `Menus.scheduled_at`); `menu_tabs.parent_tab_id` (self-referential, unbounded
nesting) + `color`; `menu_buttons.kind` (`'product'`|`'folder'` — a folder button opens a nested
`MenuTab` via `child_tab_id` instead of a product; `product_ref` is now nullable) + `width`/`height`
(1-6 × 1-4 grid-cell span — no x/y, the 6-column CSS grid packs tiles via `grid-auto-flow: dense`) +
an optional `color` override falling back to the linked product's category default colour.
`menu_builder_service.py` gained `duplicate_menu_layout()` (two-pass id-remap deep copy of the tab
tree + buttons), `schedule_layout_publish()`/`cancel_layout_scheduled_publish()`,
`update_menu_button()` (resize/recolor/relink — `color` uses the `model_fields_set` idiom from
`access_grant_service.update_grant`'s `backend_role` so an explicit `{"color": null}` clears an
override back to the category default), and the multi-select bulk actions
`bulk_recolor_menu_buttons()`/`bulk_delete_menu_buttons()`/`group_menu_buttons_into_tab()` (each
requires every selected button share one source tab). `routes/menu_layouts.py` gained matching
routes. Portal: `MenuBuilderPage.tsx` rewritten — a redesigned layouts list (colour dot, button
count, Published/Unpublished pill, active-time + day chip, last-published/edited, actions incl.
Duplicate/Hours/Schedule-publish) and the grid editor itself (rail of top-level tabs; breadcrumb;
6-column dense grid with a trailing "+" tile; pointer-based click/shift-click multi-select and
drag-move via `elementFromPoint().closest('[data-drop]')` dropping onto a rail tab or folder tile,
with a cursor-following "Moving N button(s)" ghost label; corner-handle live resize; a multi-select
floating action bar — recolor, "Move to", "Group into tab", "Delete"; a single-selection inspector —
live preview, linked-product dropdown or folder rename+"Open tab", colour palette/custom/"Category
default" reset, width/height steppers, delete). The mockup's `Import`/`Export` layout-list pills are
intentionally omitted — no export/import backend exists for `menu_layouts` (unlike Products/
Categories/Reporting Groups' Stage 19 `export_service.py`) and a non-functional button would violate
the no-half-finished-features rule. See `STAGE_STATUS.md` for full deliverables and test coverage.

**Feedback round 2 (post-Phase-2, complete).** Nine user-testing fixes — see `STAGE_STATUS.md`
"user-testing feedback round 2" for details. Notables: `modifier_groups.has_quantity` (migration
`0043` — POS may select the same option more than once, capped by `max_selections`; POS-side
enforcement is Android-stage work); modifier group rename + optimistic/instant-feedback mutations on
`ModifiersPage`/`CategoriesPage` (cache-append from the POST response, optimistic patches with
rollback); the grid editor's padded empty-slot rows + "+ Row" (visual only, empty slots aren't
persisted) and edge-zone insertion bars for drag-repositioning (folder tiles' middle 50% still
drops *into* the folder); and the SuperAdmin add-user fix — `POST /users` requires
`first_name`/`last_name` since Stage 15 but the form still sent `name` (every create 422'd), and
the raw array-shaped 422 `detail` rendered as a React child crashed the app to a blank page — all
raw `detail` reads now go through `apiErrorMessage()`, and `UserOut` exposes
`first_name`/`last_name`.

**Request latency optimization (post-feedback-round-2, complete).** Diagnosed the reported 5–10 s
delay on every action as per-request DB round-trip amplification: the auth dependencies issued 4–6
sequential queries before any route work, so each statement paid a full network RTT to the database
(compounding when API and DB are in different regions). `resolve_access`/`resolve_management_access`/
`resolve_catalog_access` now resolve via single LEFT-OUTER-joined queries (`_load_pos_context`/
`_load_mgmt_context`), cutting reads from 5–6 statements to 2 and writes from 8–10 to 5–7 with
identical error semantics. `RequestLoggingMiddleware` logs `duration_ms` + `request.slow` WARNING
(≥1 s) and returns `X-Response-Time-Ms`; the invoice-PDF route's WeasyPrint render moved off the
event loop (`asyncio.to_thread`); engine pool is env-tunable (`DB_POOL_SIZE`/`DB_MAX_OVERFLOW`/
`DB_POOL_RECYCLE_SECONDS`). Remaining fixed cost is RTT-bound — co-locating the Railway service
with the Supabase region is the deployment-side follow-up. See `STAGE_STATUS.md` "Performance —
request latency optimization".

**Efficiency hardening round (post-latency-optimization, complete).** Five fixes from an efficiency
review — see `STAGE_STATUS.md` "Efficiency hardening round". Notables: the portal's bounded-fetch
pattern (`{ limit: 200 }`) silently dropped rows past the cap — a new `fetchAll<T>()` in
`src/api/axios.ts` pages through `skip`/`limit` until a short page and now backs every catalog/admin
list fetch (backend list caps raised to `le=1000`); `InvoicesPage` instead got true server-side
pagination (50/page, Prev/Next) because invoice volume is unbounded; production log volume cut ~⅓
per request (uvicorn `--no-access-log`, `request.started`/`audit.queued` → DEBUG); sync
`resend.Emails.send` and argon2 login verification moved off the event loop
(`asyncio.to_thread`/`verify_password_async` — admin-time hashing stays sync by design); the
in-process rate limiter now evicts stale keys (was a slow, unbounded memory leak).

**Menu Studio feedback round 3 (post-efficiency-hardening, complete).** Six user-reported gaps — see
`STAGE_STATUS.md` "Menu Studio — feedback round 3" for details. Notables: `ProductsPage` gained a
modifier-attach picker (`ModifierPickerModal.tsx`, drag-to-reorder, backed by
`GET`/`PATCH .../modifiers/reorder`) and multi-select bulk actions (`POST /products/bulk` — category/
price/%-markup/tax/modifier-attach/archive, all-or-nothing, per-product audit rows); archiving a
product now cascades to detach its modifier links and remove any POS-layout buttons referencing it;
there's deliberately no bulk "Reporting Group" action or table column — reporting group is derived
through Category, not a Product column; `ModifiersPage`'s "used by N products" line now expands into
an actual product list with an add-product control; `menu_buttons` gained nullable `grid_col`/
`grid_row` (migration `0045`) plus a `PATCH .../buttons/{id}/place` route so a product/folder tile
can be dropped onto any empty grid cell, not just sequential positions; and the grid editor's 5-10s
lag (a page-specific full-tree `invalidateQueries` on every mutation, distinct from the earlier
general request-latency round) is fixed by patching the `['menu-layout', id]` cache directly from
each mutation's own (now-broadened) response instead of refetching.

**Menu Studio — POS Layout tile style redesign (post-feedback-round-3, complete).** Restyled the
grid editor's product/folder tiles from a reference POS mockup — larger rounded corners, a bolder/
larger product name and price (price switched from the table-numeral `font-mono` convention to a
bold sans figure, since these tiles model an actual POS button rather than a data table), and a
decorative round "+" quick-add badge on every unselected product tile. `MenuButtonOut` gained
`product_photo_url` (resolved from the linked product's existing `photo_url` — no migration, that
column and its upload route have existed since Stage 8/24) so a tile can show the linked product's
photo as a full-bleed background with a legibility scrim instead of a flat colour, falling back to
the flat colour tile when the product has none (true for virtually every product today — there's no
photo-upload control on `ProductsPage.tsx` yet, an existing gap this didn't take on). The rail of
top-level tabs was initially left untouched on a since-corrected reading of the request — see the
follow-up below. See `STAGE_STATUS.md` "POS Layout tile style redesign" for the full before/after
and how it was verified (a static, class-accurate mockup screenshot — this environment has no
reachable Postgres to drive the real editor end-to-end).

**Menu Studio — POS Layout tab rail style redesign (post-tile-redesign, complete).** The rail of
top-level tabs now renders as solid `tab.color`-filled blocks (bold name + button count), matching
the tile redesign's reference mockup's category sidebar, instead of a small colour dot on a neutral
list row. The active tab gets a dark/light `ring` border (the mockup's black outline, adapted to
the portal's themes); a drag-over target gets a white ring so the two states stay distinct against
an arbitrary tab colour. New tabs auto-cycle through `MENU_STUDIO_PALETTE` so they start distinctly
coloured rather than an unstyled grey; a `ColorSwatchPicker` (the same component already used for
layouts/buttons/categories) on each row lets that be changed afterward, backed by a new
`updateTabColor` mutation against `MenuTabUpdate.color` — a field the schema already accepted but
nothing in the portal exposed yet. See `STAGE_STATUS.md` "POS Layout tab rail style redesign".

**Menu Studio — POS Layout tab rail testing fixes (post-rail-redesign, complete).** Three issues
found exercising the rail redesign against a live layout, all fixed — see `STAGE_STATUS.md` "POS
Layout tab rail testing fixes". Notables: `ColorSwatchPicker` (shared by Categories, button
recolouring, and the tab rail) now portals its popover into `document.body` at a `position: fixed`
coordinate instead of a plain `position: absolute` child of the trigger, so it's never clipped by a
narrow/scrollable ancestor (the rail is exactly that); its selected-swatch indicator is now a small
white checkmark badge instead of a border, which used to blend into an already-dark or
already-light palette colour; and the rail itself is now flush edge-to-edge (no padding/gap/
rounding per row, `ring-inset` on the active/drag-over ring so it doesn't bleed into the now-
touching neighbour) rather than a list of separated rounded cards, matching the reference's stacked
square-cornered blocks.

**Standalone auth pages — dark theme consolidation + theme toggle (post-rail-testing-fixes,
complete).** User-reported: the login page's dark theme didn't match the logged-in app's. Root
cause — `LoginPage.tsx`/`ForgotPasswordPage.tsx`/`ResetPasswordPage.tsx` render outside
`Layout.tsx` (no session yet, so no sidebar) and each hard-coded its own `bg-gray-50
dark:bg-gray-900` canvas instead of `--zr-bg`, the warm cream/near-black token every authenticated
page actually sits on; the wordmark also had no dark-mode colour at all. New `AuthPageShell.tsx`
consolidates all three pages onto one shell (`bg-[var(--zr-bg)]` canvas, `text-[var(--zr-accent-
text)]` wordmark; the card itself stays `bg-white dark:bg-gray-800`, deliberately matching
`Modal.tsx`'s existing convention rather than switching to a different token) and adds a theme
toggle — none of these pages had one before, since the only prior toggle lived in the sidebar these
pages don't render. See `pos-portal/CLAUDE.md`'s "Standalone auth pages" section and
`STAGE_STATUS.md` "Standalone auth pages — dark theme consolidation + theme toggle".

**Menus tab removal (post-auth-pages, complete).** The standalone "Menus" nav tab
(`MenusPage.tsx`/`/management/menus`, its own `menus` table/router/service from the Menu Studio
redesign) was removed as redundant: it duplicated the draft/schedule/publish lifecycle Phase 2
already added directly onto `menu_layouts`, nothing in Menu Studio depended on it, and the POS read
contract (`GET /pos/menu-layout`) never consulted it in the first place. Removed the backend
router/service/schema/model, its six `MENU_*` audit actions, its `menus` `PAGE_CATALOG`/license-gate
entry (migration `0048` drops the table), and the portal page/route/nav entry/TypeScript type. See
`STAGE_STATUS.md` "Menus tab removal" and the updated `ROLE_MODEL.md` §6.

## Folder structure (backend)
```
pos-backend/
├── app/
│   ├── main.py         ← FastAPI app, router registration, middleware
│   ├── database.py     ← SQLAlchemy engine, session factory, Base
│   ├── models/         ← SQLAlchemy ORM models
│   ├── schemas/        ← Pydantic request/response schemas
│   ├── routes/         ← Route handlers (thin — logic goes in services/)
│   ├── services/       ← All business logic
│   ├── constants/      ← Audit actions, status enums, reference data
│   ├── utils/          ← Security, email, storage, dependencies
│   ├── middleware/     ← Logging, CORS, error handling
│   └── cli.py          ← Management CLI: bootstrap, seed commands
├── tests/              ← unit/ and integration/ mirror app/ structure
├── alembic/            ← Database migrations
└── docker-compose.yml
```
New files always go in the correct folder. Never create files outside this structure.

## Logging
Logging is threaded through every stage, not a separate feature: structlog (JSON in prod via
`LOG_FORMAT`), request-ID middleware, and the `audit_logs` table exist from Stage 1. Every
auth/CRUD/license/invoice write audits via `log_action()` (`app/services/audit_service.py`);
nightly jobs audit with `actor_type='system'`.

## Absolute rules — no exceptions
1. Type hint every function parameter and return value.
2. Docstring every function, class, and module.
3. Inline comment every non-obvious line.
4. Every monetary column ends in `_cents` and is stored as BIGINT.
5. Every boolean column starts with `is_` or `has_`.
6. Routes are thin — all logic lives in services.
7. Every service write calls `log_action()` in the same transaction.
8. Use constants from `app/constants/` — never hardcode action strings or status values.
9. Never use float for money — int (cents) for storage, Decimal for calculation.
10. Never mock the database in tests — use the real test DB fixture.
11. Every test for a write must assert the correct audit_logs row was written.
12. Every route must declare a `response_model`.
13. Every list route must support pagination with `skip` and `limit`.
14. Never catch an exception and do nothing — log it at ERROR and re-raise.
15. Never commit `.env` files, never store plaintext passwords, tokens, or PINs.
16. Every portal page must be mobile-friendly: `overflow-x-auto` on table containers,
    responsive padding (`p-4 sm:p-6`), `flex-wrap` on header/filter rows. Test at 375px width.
17. Never build SQL with f-strings or string concatenation.
18. Never skip writing tests for a completed task.
19. Never leave a TODO comment without an issue number: `# TODO(#42): description`.
20. Never run a migration against production without reviewing it first.
