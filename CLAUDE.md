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
See `STAGE_STATUS.md` for full deliverables. **Stage 21 is next (not yet started):** see
`ROADMAP.md` Phase 7 for full detail. Do not begin Stage 22+ work yet.

**Stages 21–24 scope (planned, not started):** see `ROADMAP.md` Phases 7–9 for full detail. Summary
(Stages 16–20 above are complete — see their own paragraphs and `STAGE_STATUS.md`):
- **21 — Invoice Reporting:** filtered list + XLSX export, detail view, PDF export (standard layout),
  and a change-log panel sourced from the existing `audit_logs` table filtered by
  `entity_type='invoice'` — no new table, `invoice_service.py` already audits every mutation with
  before/after state.
- **22 — Variants & Combos Portal Pages:** one combined portal page/sidebar entry for Variants and
  Combos (not Modifiers — Modifiers stay edited inline within the Product page). New `ref` codes
  (`VAR-000001`, `CMB-000001`) and a `display_name` field on both Variant and Combo (not on
  Modifiers). Filters, inline edit, import/export via Stage 19's framework.
- **23 — POS Menu Builder:** new `menu_layouts` / `menu_tabs` / `menu_buttons` tables. Buttons
  reference products by `ref` code (not FK), so a layout survives product recreation. Prototype
  scope: single-level tabs + buttons only, no nested sub-menus. More than one layout can be
  published at once (e.g. per-site or day-part menus).
- **24 — Product Model Extensions:** surface the dormant `products.ref` DB column (added in
  migration `0013`, never wired into the ORM model/schema) as "product code"; add `print_name`
  (falls back to `name`); add `is_open_item` with a new `can_use_open_item` capability flag +
  optional `open_item_max_price_cents` ceiling on `AccessProfile` (a capability flag, not a page
  grant, since it's an action permission not a page). `description` and `photo_url` already exist
  on Product — no work needed there.

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
