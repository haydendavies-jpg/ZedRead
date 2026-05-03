# ZedRead POS

Android point-of-sale system with a FastAPI/PostgreSQL backend and a React super-admin portal.

## What it is

Multi-tenant POS platform. The hierarchy is **Group → Brand → Site**. A Group can contain many Brands (e.g. restaurant chains), each Brand can have many Sites (locations), and each Site runs the Android POS app.

## Tech stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.12, FastAPI, SQLAlchemy (async), Alembic |
| Database | PostgreSQL (Supabase in production) |
| Task queue | Celery + Redis |
| Portal frontend | React, TypeScript, Vite, Tailwind, React Router |
| Android POS app | Kotlin, Jetpack Compose, Retrofit, Hilt, Room |
| Logging | structlog → Grafana Cloud Loki |
| Hosting | Railway (API), Vercel (portal), Supabase (DB) |

## Build phases

| Phase | Stages | Deliverable |
|---|---|---|
| 1 — Foundation & Portal | 1–6 | Super admin portal, hierarchy management, license management. Live at Stage 6. |
| 2 — POS Catalog | 7–9 | POS auth, product catalog, variants, modifiers, combos. |
| 3 — Transactions | 10–12 | Invoice engine, payments, reporting. Full backend live at Stage 12. |
| 4 — Android App | 13–14 | Complete POS Android application. |

## Stage summary

| # | Stage | What exists after |
|---|---|---|
| 1 | Project Setup + Logging | Folder structure, Docker, test harness, structlog, audit_logs table, log_action() helper |
| 2 | Portal Auth | Portal login, JWT, bootstrap CLI, auth audit logs |
| 3 | Hierarchy CRUD API | Groups, brands, sites API with reseller filtering and audit logging |
| 4 | License Management | Licenses, invoices, device registration, nightly expiry job |
| 5 | Portal Frontend | Working React portal for all CRUD and license management |
| 6 | Deploy Phase 1 | **Portal live.** API on Railway, DB on Supabase, logs in Grafana Cloud |
| 7 | POS Auth & Users | POS login, PIN, invite flow, access profiles, permission enforcement |
| 8 | Product Catalog | Products, categories, tax config, site overrides, photo upload |
| 9 | Variants, Modifiers, Combos | Advanced product features with circular reference protection |
| 10 | Invoice Engine | Sales, payments, void, refund, split payments — all audit logged |
| 11 | Reporting | 8 reporting views, scope-enforced API routes |
| 12 | Deploy Phase 2 | **Full backend live.** All routes available and tested |
| 13 | Android — Auth & Catalog | Login, PIN, site selector, product grid, cart |
| 14 | Android — Payments & Printing | Payments, docket printing, switch user, inline auth |

**Stage 6 = first commercially usable product** (reseller can onboard customers via portal).  
**Stage 12 = complete backend** (full audit trail, all routes live).  
**Stage 14 = complete system** (Android app ships).

## Local development

```bash
# Start all services (API, Postgres, test Postgres, Redis)
docker compose up

# Run database migrations
alembic upgrade head

# Bootstrap the first super admin
python -m app.cli bootstrap-super-admin

# Run tests
pytest

# Start the API
uvicorn app.main:app --reload
```

## Design document

All features are specified in **pos_master_v5.docx**. Reference the relevant chapter before implementing any feature. Never implement anything that contradicts the design doc without flagging it first.

## Key rules

- Business logic lives in `services/` — never in route handlers
- Monetary values stored as integers in cents — never float
- Every write operation calls `log_action()` in the same transaction
- Every completed task must have tests
- See `CLAUDE.md` for full project rules
