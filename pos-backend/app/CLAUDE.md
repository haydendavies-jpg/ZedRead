# ZedRead — Python & FastAPI Style Guide

Single source of truth for backend code style; applies to every Python file in `app/`.
When a pattern is missing, add it here before implementing it.
Project-wide absolute rules (money, booleans, audit, pagination, etc.) live in the root `CLAUDE.md`.

---

## 1 — File & folder structure

- **One responsibility per file.** Past ~200 lines, check whether a second responsibility should split out.
  Example split: `models/invoice.py` (ORM), `schemas/invoice.py` (Pydantic), `routes/invoices.py`
  (thin handlers), `services/invoice_service.py` (all logic), constants in `constants/`.
- **Tests mirror source paths**: `app/services/invoice_service.py` → `tests/unit/test_invoice_service.py`.
- **Route order within a file**: list → get one → create → update → actions → delete.

## 2 — Naming

| Thing | Convention | Example |
|---|---|---|
| Modules | snake_case | `invoice_service.py` |
| Classes / models / schemas | PascalCase (models singular; schemas suffixed) | `Invoice`, `InvoiceCreate`, `InvoiceResponse` |
| Functions, variables | snake_case | `calculate_tax()`, `amount_cents` |
| Constants | UPPER_SNAKE_CASE | `INVOICE_PAID` |
| Tables | snake_case plural | `invoice_line_items` |
| Columns | snake_case; PKs `id`; FKs `{singular}_id` | `brand_id`, `created_at` |
| Route functions | snake_case verb phrase | `create_invoice` |
| Private helpers (single-module) | `_` prefix | `_get_invoice_or_404()` |
| Test functions | `test_` + subject + scenario | `test_calculate_tax_inclusive_10_percent` |

Monetary columns end in `_cents` (int); booleans start with `is_`/`has_` (root rules 4–5).

## 3 — Comments & docstrings

- Module docstring on line 1, one sentence.
- Every function: docstring in Args / Returns / Raises format.
- Inline comment any line that took more than 3 seconds of thought — money arithmetic, magic
  numbers (cite design doc chapter), non-obvious conditionals, workarounds, index/constraint choices.
- TODOs carry an issue number: `# TODO(#142): …` (root rule 19).

## 4 — Function design

- One responsibility; if the docstring says "and", consider splitting.
- Soft cap ~40 lines — a well-structured 50-line function beats two badly split 20-line ones.
- Early returns over nested conditionals; keep the happy path at the left margin.

## 5 — Error handling

| Situation | Code | Message pattern |
|---|---|---|
| Not found | 404 | `'Invoice not found'` |
| Business rule violated | 400 | Plain English: `'Category does not belong to this brand'` |
| Not authenticated | 401 | `'Not authenticated'` (auth dependency) |
| Not permitted | 403 | `'Insufficient permissions'` (permission dependency) |
| Already exists | 409 | `'Device already registered to this license'` |
| Too large | 413 | `'File exceeds the 500KB limit'` |
| Validation | 422 | Automatic from Pydantic |

Never swallow exceptions — log at ERROR with `error=` kwarg and re-raise (root rule 14).

## 6 — Database patterns

- **Always use the ORM.** `text()` with bound parameters only when the ORM cannot express the
  query (e.g. reporting views). Never f-string/concatenate SQL (root rule 17).
- Entity selects (`select(Invoice).where(...)`) are the norm. Select individual columns when a
  query is hot or wide; never write literal `SELECT *` inside `text()` SQL.
- **One transaction per service call**: the business write and its `log_action()` row commit
  together or roll back together.

```python
async def create_product(db: AsyncSession, payload: ProductCreate, actor: User) -> Product:
    """Create a product and write the audit log in the same transaction."""
    product = Product(**payload.model_dump())
    db.add(product)
    await log_action(
        db=db, action=PRODUCT_CREATED,
        actor_id=actor.id, actor_email=actor.email, actor_name=actor.name,
        entity_type='product', entity_id=str(product.id),
        after_state={'name': product.name, 'price': product.base_price_cents},
    )
    await db.commit()  # Both rows commit here or both roll back
    await db.refresh(product)
    return product
```

- After every model change: `alembic revision --autogenerate -m "description"`.
  Review before running against production (root rule 20).

## 7 — FastAPI patterns

- **Thin handlers**: a route calls one service function and returns the result. Conditional
  logic, queries, and calculations live in the service layer.
- `response_model` on every route (root rule 12).
- Pagination on every list route (root rule 13):

```python
skip: int = Query(default=0, ge=0),
limit: int = Query(default=50, ge=1, le=1000),
```

## 8 — Money arithmetic

Never float. Store int cents; calculate with `decimal.Decimal` and `ROUND_HALF_UP`.

```python
from decimal import Decimal, ROUND_HALF_UP

# User input → cents
cents = int((Decimal(str(user_input)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

# Back-calculate inclusive tax: tax = gross - (gross / (1 + rate))
tax_cents = int(
    (amount_cents - (Decimal(amount_cents) / (1 + rate_percent / 100)))
    .quantize(Decimal('1'), rounding=ROUND_HALF_UP)
)
```

Tax rules: **inclusive** — tax already in price, back-calculate; **exclusive** — `tax = gross * rate`,
add on top; **compound** — GST first, then PST on the gross (not on the GST-inclusive amount).

## 9 — Logging

```python
import structlog
log = structlog.get_logger(__name__)

log.info('invoice.voiding', invoice_id=str(invoice_id), actor_id=str(actor.id))  # kwargs, never f-strings
```

- Event names: dot-separated lowercase `resource.action[.outcome]`
  (`invoice.void.complete`, `auth.login.failed` — never include the failure reason for auth events).
- Levels: DEBUG dev-only · INFO entry to every writing service function · WARNING recoverable
  surprises · ERROR caught failures (always `error=` kwarg) · CRITICAL app cannot function.
- Never log passwords, tokens, PINs, or full request bodies.

## 10 — Audit logging

Every data-modifying service function calls `log_action()` (`app/services/audit_service.py`)
in the same transaction, using action constants from `app/constants/audit_actions.py`.
Snapshot `actor_email`/`actor_name` at action time. System jobs use `ActorType.SYSTEM`.

### `log_action()` calling convention (CRITICAL)

Every parameter is keyword-only (bare `*` in the signature) — positional `db` raises `TypeError`
at runtime with no compile-time warning.

```python
await log_action(
    db=db,
    actor_id=actor.id,          # uuid.UUID — NOT str(actor.id)
    actor_email=actor.email,
    actor_name=actor.name,
    action=USER_CREATED,
    entity_type="user",
    entity_id=str(user.id),     # entity_id IS a str
    after_state={"name": user.name},
)
```

Key types: `db` → `AsyncSession`; `actor_id` → `uuid.UUID | None` (never `str(...)`);
`actor_type` → `ActorType` enum — omit for user actions (defaults to `ActorType.USER`),
set `ActorType.SYSTEM` for Celery jobs; `entity_id` → `str`.

## 11 — Pydantic v2 UUID rule (CRITICAL)

ORM models return `uuid.UUID` objects; Pydantic v2 with `from_attributes=True` does **not**
coerce them to `str`. A response schema field typed `str` raises `ValidationError` at
serialization time: the DB write succeeds but the HTTP response is a 500, so the frontend's
`onSuccess` never fires. **Always type UUID fields as `uuid.UUID` in response schemas** —
FastAPI serializes them to JSON strings automatically.

```python
class UserOut(BaseModel):
    id: uuid.UUID        # Correct — never `id: str`
    brand_id: uuid.UUID
    model_config = {"from_attributes": True}
```
