# ZedRead POS

Android point-of-sale system with a FastAPI/PostgreSQL backend and a React super-admin portal.

## What it is

Multi-tenant POS platform. The hierarchy is **Group → Brand → Site**. A Group can contain many Brands (e.g. restaurant chains), each Brand can have many Sites (locations), and each Site runs the Android POS app.

## Tech stack

| Layer | Technology | Hosting |
|---|---|---|
| Backend API | Python 3.12, FastAPI, SQLAlchemy (async), Alembic | Railway |
| Database | PostgreSQL 16 | Supabase |
| File storage | Product photos | Supabase Storage |
| Task queue | Celery + Redis | Railway |
| Portal frontend | React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query | Railway |
| Android POS app | Kotlin, Jetpack Compose, Retrofit, Hilt, Room | — |
| Logging | structlog → Grafana Cloud Loki | — |

> If any of these change, update this table **and** `ARCHITECTURE.md`.

## Build phases

| Phase | Stages | Deliverable | Status |
|---|---|---|---|
| 1 — Foundation & Portal | 1–6 | Super admin portal, hierarchy management, license management | ✅ Complete |
| 2 — POS Catalog | 7–9 | POS auth, product catalog, variants, modifiers, combos | ✅ Complete |
| 3 — Transactions | 10–12 | Invoice engine, payments, reporting | ✅ Complete |
| 4 — Android App | 13–14 | Complete POS Android application | 🚧 In Progress |
| 5 — Identity & Permissions Redesign | 15 | SuperAdmin/User rename, 5-role model (`ROLE_MODEL.md`) | 🚧 In Progress |

## Stage summary

| # | Stage | What exists after |
|---|---|---|
| 1 | Project Setup + Logging | Folder structure, Docker, test harness, structlog, `audit_logs` table, `log_action()` helper |
| 2 | Portal Auth | Portal login, JWT, bootstrap CLI, auth audit logs |
| 3 | Hierarchy CRUD API | Groups, brands, sites API with reseller filtering and audit logging |
| 4 | License Management | Licenses, invoices, device registration, nightly expiry Celery job |
| 5 | Portal Frontend | Working React portal for all CRUD and license management |
| 6 | Deploy Phase 1 | **Portal live.** API + portal on Railway, DB on Supabase, logs in Grafana Cloud |
| 7 | POS Auth & Users | POS login, PIN, invite flow, access profiles, permission enforcement |
| 8 | Product Catalog | Products, categories, tax config, site overrides, photo upload to Supabase Storage |
| 9 | Variants, Modifiers, Combos | Advanced product features with circular reference protection |
| 10 | Invoice Engine | Sales, payments, void, refund, split payments — all audit logged |
| 11 | Reporting | 8 PostgreSQL reporting views, scope-enforced API routes |
| 12 | Deploy Phase 2 | **Full backend live.** All routes available and tested |
| 15 | Identity & Permissions Redesign | SuperAdmin/User rename, 5-role model, per-page permissions |
| 16 | Reporting Groups | Brand-scoped grouping above Categories |
| 17 | Delegated User Creation | Scope- and rank-limited user creation from the portal |
| 18 | Permission Scopes Portal UI | First portal UI for the Stage 15 page-permission system |
| 19 | Bulk Import/Export (XLSX) | Template/full export + import for Products, Categories, Reporting Groups |
| 20 | Table UX | Inline edit, filters, and new columns on the catalog pages |
| 21 | Invoice Reporting | Filtered list, XLSX export, detail view, PDF export, change log |
| 22 | Variants & Combos Portal Pages | Combined portal page, human-readable codes, display names |
| 23 | POS Menu Builder | Graphical tab/button menu layout + publish pipeline |
| 24 | Product Model Extensions | Product code, print name, open item |
| 25 | Android — Auth & Catalog | Login, PIN, site selector, product grid, cart |
| 26 | Android — Payments & Printing | Payments, docket printing, switch user, inline auth |

**Stage 6 = first commercially usable product** (reseller can onboard customers via portal).  
**Stage 12 = complete backend** (full audit trail, all routes live).  
**Stage 26 = complete system** (Android app ships).

## Local development

```bash
# Start all services (API, Postgres, test Postgres, Redis)
docker compose up

# Run database migrations
cd pos-backend
alembic upgrade head

# Bootstrap the first super admin
python -m app.cli bootstrap-super-admin

# Run tests
pytest

# Start the API
uvicorn app.main:app --reload

# Start the portal
cd pos-portal
npm install
npm run dev
```

## Documentation

| File | What it covers |
|---|---|
| `ARCHITECTURE.md` | System overview, tech stack, tenant hierarchy, auth flows, deployment topology |
| `DATA_MODEL.md` | All database tables, relationships, and design reasoning |
| `DECISIONS.md` | Architecture Decision Records — key choices and why |
| `STAGE_STATUS.md` | Per-stage build checklist — what is done, in progress, and upcoming |
| `ROADMAP.md` | Phase breakdown and post-Phase 4 backlog |
| `CLAUDE.md` | Project rules (absolute — all contributors must read) |
| `pos-backend/app/CLAUDE.md` | Backend code style and FastAPI patterns |
| `tests/CLAUDE.md` | Testing rules |
| `pos-portal/CLAUDE.md` | React style, components, and brand |

## Key rules

- Business logic lives in `services/` — never in route handlers
- Monetary values stored as integers in cents — never float
- Every write operation calls `log_action()` in the same transaction
- Every completed task must have tests
- See `CLAUDE.md` for the full list of absolute rules
