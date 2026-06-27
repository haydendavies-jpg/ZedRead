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

Transaction flow: Invoice → line items (snapshot product/price) → modifiers → discount → tax breakdown
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

1. **Portal Access JWT** — PortalUser (super-admin). Issued by `portal_auth_service`.
2. **Management JWT** — POS user who also has portal-capable access grant; issued after a scope-selection
   step (`/auth/portal/management-token`) when the user has multiple grants.
3. **POS Access JWT** — terminal-scoped (single site); PIN verification returns a fresh token for
   quick user-switching without full logout.

Tokens stored in localStorage (portal) or DataStore (Android). No rate-limiting/sessions exist.

## Routes inventory (pos-backend/app/routes)

| File | Endpoints |
|---|---|
| portal_auth.py | login, refresh, management-token, mgmt-refresh, change-password |
| pos_auth.py | login, pin/set, pin/verify |
| brands.py / groups.py / sites.py | CRUD + suspend/activate, paginated list/filter |
| products.py | CRUD, soft-delete, photo upload (Supabase Storage) |
| categories.py | list/create/update (system categories protected) |
| invoices.py | create, line-items, modifiers, discount, pay, void, refund |
| tax.py | tax category/rate management |
| licenses.py | CRUD, disable/enable |
| pos_users.py / portal_users.py | CRUD, suspend/activate, PIN admin set, grants |
| access_grants.py / access_profiles | grant CRUD, permission tiers |
| reports.py | daily-sales, product-revenue, payment-methods, tax-collected |
| modifiers.py / combos.py / variants.py | catalog extras management |
| site_overrides.py | per-site price/availability overrides |
| pos_devices.py | terminal device registration |
| user_invites.py / license_invoices.py | onboarding invites, recurring license billing |

## Models inventory (pos-backend/app/models)

Hierarchy: `groups` ← `brands` (group_id) ← `sites` (brand_id).
Catalog: `categories`, `products` (base_price_cents BIGINT), `product_variants`, `product_combo_groups/options`,
`modifier_groups/options`, `product_modifier_group_links` (M:N), `tax_categories`, `tax_rates`.
Identity: `pos_users` (brand-scoped), `portal_users` (super-admin, no scope), `user_access_grants`
(site|brand|group scope + access_profile_id), `access_profiles` (permission tiers, JSON perms), `user_pins`.
Transactions: `invoices`, `invoice_line_items` (snapshotted name/price), `invoice_line_modifiers`,
`invoice_tax_breakdowns`, `payments`.
Billing: `licenses` (site_id, one per site), `license_invoices`.
Overrides: `site_product_overrides`, `site_variant_overrides`.
Ops: `user_pos_sessions`, `pos_devices`, `audit_logs` (immutable), `user_invites`.

## Terminology

| Term | Meaning |
|---|---|
| Group | Top-level tenant, no parent |
| Brand | Business under a Group; owns catalog, staff, access profiles |
| Site | Location under a Brand; one license, one Android terminal |
| POS User | Brand-scoped staff; logs into terminal; granted access to sites |
| Portal User | Super-admin; unrelated to Brand/Site scoping |
| Access Grant | Join record: user + scope (site/brand/group) + Access Profile |
| Access Profile | Named permission tier (JSON perms) belonging to a Brand |
| Management JWT | Issued to a POS user with portal access after they pick a scope/grant |
| PIN | Secondary credential for fast terminal user-switching (separate from login password) |
| Combo | Bundled choices baked into one product (`product_combo_groups/options`) |
| Modifier | Reusable add-on attachable to many products via join table |
| Site Override | Per-site price/availability exception layered over brand-wide catalog price |

## Known discrepancies to watch for vs written summaries / design doc

- Redis is **not** a cache/session/rate-limit layer — it's a Celery broker for one nightly job only.
- No session-based auth exists anywhere — fully stateless JWT across all three token types.
- Portal has no backend logic of its own — pure static SPA REST client.
- Live code already covers invoices/modifiers/combos/reports (Phase 3 territory per CLAUDE.md rollout
  table) — if a summary claims an earlier active stage, reconcile against actual route/model inventory above.

*Last mapped: 2026-06-27. Re-verify against code if it has changed significantly since.*
