# ZedRead POS — Project Rules

## What this project is
Android POS system with a FastAPI/PostgreSQL backend and a React super-admin portal.
Multi-tenant hierarchy: Group → Brand → Site.

## Design document
**pos_master_v5.docx** — reference the relevant chapter before implementing any feature.
Never implement a feature that contradicts the design document without flagging it first.

## Architecture map (ground truth)
**ARCHITECTURE_MAP.md** — a functional map of the actual codebase (routes, models, Redis usage,
deployment topology, terminology), derived from reading code rather than docs/comments. Read this
first when picking up the project in a new session. If it conflicts with the design doc or other
written summaries, the code (and this map) wins — flag the conflict.

## Rollout plan
The project is built in 4 phases across 14 stages. Always work within the current stage.
Never implement features from future stages unless explicitly instructed.

| Phase | Stages | Summary |
|---|---|---|
| 1 — Foundation & Portal | 1–6 | DB, auth, hierarchy, licenses, React portal, deploy |
| 2 — POS Catalog | 7–9 | POS auth, products, variants, modifiers, combos |
| 3 — Transactions | 10–12 | Invoice engine, payments, reporting, deploy |
| 4 — Android App | 13–14 | Kotlin + Jetpack Compose POS application |

## Folder structure
```
pos-backend/
├── app/
│   ├── main.py              ← FastAPI app, router registration, middleware
│   ├── database.py          ← SQLAlchemy engine, session factory, Base
│   ├── models/              ← SQLAlchemy ORM models
│   ├── schemas/             ← Pydantic request/response schemas
│   ├── routes/              ← FastAPI route handlers (thin — logic goes in services/)
│   ├── services/            ← All business logic
│   ├── constants/           ← String constants: audit actions, status enums
│   ├── utils/               ← Shared utilities: security, formatting, ID generation
│   ├── middleware/          ← FastAPI middleware: logging, CORS, error handling
│   └── cli.py               ← Management CLI: bootstrap, seed commands
├── tests/
│   ├── conftest.py          ← Shared fixtures: DB engine, test client, test users
│   ├── unit/                ← Unit tests mirroring app/ structure
│   └── integration/         ← Integration tests mirroring app/routes/ structure
├── alembic/                 ← Database migrations
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

New files always go in the correct folder. Never create files outside this structure.

## Logging is threaded throughout — not a separate stage

Logging is present from Stage 1 and grows with the system.

| Component | Stage | What gets added |
|---|---|---|
| structlog setup | 1 | JSON renderer for prod, ColourRenderer for dev, controlled by LOG_FORMAT env var |
| Request ID middleware | 1 | Every request gets a UUID; all log lines carry the same request_id |
| audit_logs table | 1 | Created in the first migration — exists from day one |
| log_action() helper | 1 | app/services/audit_service.py — written and unit-tested before anything calls it |
| Portal auth audit logging | 2 | Login and logout write audit rows |
| Hierarchy CRUD audit logging | 3 | Every group/brand/site create and status change writes an audit row |
| License audit logging | 4 | License created/disabled/enabled/expired; nightly job uses actor_type = 'system' |
| POS auth audit logging | 7 | POS login, logout, failed login, PIN set, PIN reset |
| Product audit logging | 8 | Product created, updated, price changed, deactivated |
| Invoice audit logging | 10 | Invoice paid, voided, refunded, discount applied |

## Sub-rules
- Code style, naming, and FastAPI patterns: see **app/CLAUDE.md**
- Testing rules: see **tests/CLAUDE.md**
- Portal (React) style, components, and brand: see **pos-portal/CLAUDE.md**

## Absolute rules — no exceptions

These 15 rules apply to every task in every stage:

1. Type hint every function parameter and return value.
2. Docstring every function, class, and module.
3. Inline comment every non-obvious line.
4. Every monetary column ends in `_cents` and is stored as BIGINT.
5. Every boolean column starts with `is_` or `has_`.
6. Routes are thin — all logic lives in services.
7. Every service write calls `log_action()` in the same transaction.
8. Use constants from `app/constants/` — never hardcode action strings or status values.
9. Never use float for money — use int (cents) for storage, Decimal for calculation.
10. Never mock the database in tests — use the real test DB fixture.
11. Every test for a write must assert the correct audit_logs row was written.
12. Every route must declare a `response_model`.
13. Every list route must support pagination with `skip` and `limit`.
14. Never catch an exception and do nothing — log it at ERROR and re-raise.
15. Never commit `.env` files, never store plaintext passwords, tokens, or PINs.
16. Every portal page must be mobile-friendly: use `overflow-x-auto` on all table containers, responsive padding (`p-4 sm:p-6`), and `flex-wrap` on header/filter rows so they stack on narrow screens. Test layouts at 375px width before marking a task complete.

Additional rules:
- Never build SQL with f-strings or string concatenation.
- Never skip writing tests for a completed task.
- Never leave a TODO comment without a GitHub issue number: `# TODO(#42): description`
- Never run a migration against production without reviewing it first.
