# ZedRead POS — Project Rules

## What this project is
Android POS system with a FastAPI/PostgreSQL backend.
Multi-tenant hierarchy: Group → Brand → Site.

## Design document
**pos_master_v5.docx** — reference the relevant chapter before implementing any feature.
Never implement a feature that contradicts the design document without flagging it first.

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

## Sub-rules
- Code style, naming, and FastAPI patterns: see **app/CLAUDE.md**
- Testing rules: see **tests/CLAUDE.md**

## Absolute rules — no exceptions
- Never put business logic in route handlers — it belongs in services/
- Never store plaintext passwords, tokens, or PINs
- Never use float for monetary values — use int (cents) for storage
- Never mock the database in tests — use the real test DB fixture
- Never hardcode status strings or action names — use constants from app/constants/
- Never build SQL with f-strings or string concatenation
- Never commit .env files
- Never skip writing tests for a completed task
- Never leave a TODO comment without a GitHub issue number: # TODO(#42): description
- Never run a migration against production without reviewing it first
