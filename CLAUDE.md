# ZedRead POS — Project Rules

## What this project is
Android POS system with a FastAPI/PostgreSQL backend and a React super-admin portal.
Multi-tenant hierarchy: Group → Brand → Site.

## Read these first
- **ARCHITECTURE_MAP.md** — functional map of the actual codebase (routes, models, deployment,
  terminology), derived from code. Read this when picking up the project in a new session.
  If it conflicts with any other doc, the code (and this map) wins — flag the conflict.
- **pos_master_v5.docx** — design document. Reference the relevant chapter before implementing
  a feature; never contradict it without flagging first.

## Scoped rules (auto-loaded when working in those directories)
- Backend code style, naming, FastAPI patterns: `pos-backend/app/CLAUDE.md`
- Testing rules and fixtures: `pos-backend/tests/CLAUDE.md`
- Portal (React) style, components, brand: `pos-portal/CLAUDE.md`

## Rollout plan
Built in 5 phases across 15 stages. Work within the current stage only; never implement
future-stage features unless explicitly instructed.

| Phase | Stages | Summary |
|---|---|---|
| 1 — Foundation & Portal | 1–6 | DB, auth, hierarchy, licenses, React portal, deploy |
| 2 — POS Catalog | 7–9 | POS auth, products, variants, modifiers, combos |
| 3 — Transactions | 10–12 | Invoice engine, payments, reporting, deploy |
| 4 — Android App | 13–14 | Kotlin + Jetpack Compose POS application |
| 5 — Identity & Permissions Redesign | 15 | Rename + 5-role model — see `ROLE_MODEL.md` |

**Stage 15 scope (current):** implement the rename and role/permission model in `ROLE_MODEL.md` —
SuperAdmin (Admin/Reseller Staff), User (Master User/Admin/Reporting Only/Manager/Staff),
required-field rules, access_profiles replaced by the 5 roles, per-page permission grants within
the 5 page categories, license gating, and cross-identity login disambiguation. The per-category
page list (§6 of `ROLE_MODEL.md`) is still open — define it during this stage, then update
`ROLE_MODEL.md` to record it as resolved.

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
