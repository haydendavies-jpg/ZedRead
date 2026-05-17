# ZedRead — Application Code Rules
# Python & FastAPI Style Guide

This file is the single source of truth for backend code style. It applies to every Python file
in `app/`. When a pattern is missing, add it here before asking Claude Code to implement it.

---

## 1 — File & Folder Structure

### 1.1 One responsibility per file

Each file has one job. When a file grows beyond ~200 lines, consider whether it has taken on
a second responsibility that should be split out.

| File | What it contains |
|---|---|
| `app/models/invoice.py` | SQLAlchemy ORM models for invoices, line items, payments, tax breakdown |
| `app/schemas/invoice.py` | Pydantic schemas: InvoiceCreate, InvoiceUpdate, InvoiceResponse |
| `app/routes/invoices.py` | FastAPI route handlers — thin, each calls one service function |
| `app/services/invoice_service.py` | All invoice business logic: create, pay, void, refund |
| `app/constants/audit_actions.py` | Audit action string constants only: `INVOICE_PAID = 'invoice.paid'` |
| `app/constants/statuses.py` | Status value constants: InvoiceStatus, LicenseStatus enums |

### 1.2 Test files mirror source files

Every source file has a corresponding test file. The path mirrors the source path under `tests/`.

```
# Source
app/services/invoice_service.py

# Test
tests/unit/test_invoice_service.py
```

### 1.3 Route file order

Within each route file, define routes in this order:
1. List — `GET /`
2. Get one — `GET /{id}`
3. Create — `POST /`
4. Update — `PATCH /{id}`
5. Actions — `POST /{id}/action`
6. Delete — `DELETE /{id}`

---

## 2 — Naming Conventions

### 2.1 General naming

| Thing | Convention | Example |
|---|---|---|
| Python modules (files) | snake_case | `invoice_service.py`, `tax_calculation.py` |
| Classes | PascalCase | `InvoiceService`, `TaxCategory`, `PortalUser` |
| Functions and methods | snake_case | `calculate_tax()`, `get_invoice_or_404()` |
| Variables | snake_case | `invoice_id`, `amount_cents`, `actor_email` |
| Constants | UPPER_SNAKE_CASE | `INVOICE_PAID`, `MAX_PIN_LENGTH` |
| Pydantic schemas | PascalCase + suffix | `InvoiceCreate`, `InvoiceResponse`, `InvoiceUpdate` |
| SQLAlchemy models | PascalCase singular | `Invoice`, `LineItem` (not `Invoices`) |
| Database tables | snake_case plural | `invoices`, `invoice_line_items`, `tax_categories` |
| Database columns | snake_case | `created_at`, `brand_id`, `price_inc_tax_cents` |
| FastAPI route functions | snake_case verb phrase | `create_invoice`, `get_invoice`, `void_invoice` |
| Test functions | `test_` + subject + scenario | `test_calculate_tax_inclusive_10_percent` |
| Private helpers | `_` prefix | `_get_invoice_or_404()`, `_apply_void()` |

### 2.2 Monetary column naming

Every column storing a monetary value must end in `_cents`. This makes it immediately obvious
that the value is an integer in the smallest currency unit, not a decimal or float.

```python
# Correct
price_inc_tax_cents: int
price_ex_tax_cents: int
modifier_total_cents: int
amount_paid_cents: int

# Wrong
price: float
price_including_tax: Decimal
amount_paid: int
```

### 2.3 Boolean column naming

Boolean columns must start with `is_` or `has_`.

```python
# Correct
is_active: bool
is_taxable: bool
is_weighted: bool
has_variants: bool

# Wrong
active: bool
taxable: bool
weighted: bool
```

### 2.4 ID column naming

Foreign key columns use the singular table name with `_id` suffix. Primary keys are always `id`.

```python
# Correct
id: UUID           # primary key
brand_id: UUID     # FK to brands
site_id: UUID      # FK to sites
actor_id: UUID     # FK to users

# Wrong
brand: UUID
site_uuid: UUID
userId: UUID       # wrong case
```

---

## 3 — Comments & Docstrings

### 3.1 Module docstrings

Every Python file starts with a module-level docstring on line 1. One sentence.

```python
"""Service layer for invoice creation, payment, voiding, and refunding."""

from decimal import Decimal
```

### 3.2 Function docstrings

Every function has a docstring using Args / Returns / Raises format.

```python
async def resolve_products_for_site(
    db: AsyncSession,
    site_id: UUID,
) -> list[ResolvedProduct]:
    """
    Build the product catalog for a site.

    Merges brand-level products with site overrides.
    Excluded products are filtered out. Site prices replace brand prices where set.

    Args:
        db: Database session.
        site_id: The site to resolve products for.

    Returns:
        List of ResolvedProduct with effective prices.
    """
```

### 3.3 Inline comments

Add an inline comment on any line that is not immediately obvious. The standard: if you had
to think about the line for more than 3 seconds, it needs a comment.

Lines that always need a comment:

| Situation | Example comment |
|---|---|
| Money arithmetic | `# Back-calculate tax from gross: tax = gross - (gross / (1 + rate))` |
| Magic numbers | `# 500_000 = 500KB limit enforced by the design doc (Ch 6)` |
| Non-obvious conditionals | `# Empty array means all sites permitted — see Ch 10.3` |
| Workarounds | `# asyncpg does not support Decimal natively — convert to float for bind param` |
| Index/constraint decisions | `# Partial index: only one active device per license at a time` |

### 3.4 TODO comments

```python
# Correct
# TODO(#142): Add webhook notification when license expires

# Wrong
# TODO: fix this later
# FIXME
```

---

## 4 — Function Design

### 4.1 One responsibility per function

If a function's docstring says "and", consider splitting it.

```python
# Correct — one job each
async def void_invoice(...) -> Invoice:
    invoice = await _get_or_404(db, id)
    _check_not_already_voided(invoice)
    await _apply_void(db, invoice, actor)
    await log_action(db, actor, INVOICE_VOIDED, ...)
    await db.commit()
    return invoice

# Wrong — mixed responsibilities
async def void_invoice_and_notify(...):
    """Void invoice and send email."""
    # 80 lines of mixed voiding logic, email sending, and audit writing
```

### 4.2 Maximum function length

Functions should not exceed 40 lines. A well-structured 50-line function is better than two
poorly-structured 20-line functions — use judgement. Long functions are a signal to look for
a split.

### 4.3 Early returns over nested conditions

Return early when a condition is not met rather than nesting the happy path.

```python
# Correct
async def pay_invoice(...):
    if invoice.status != 'open':
        raise HTTPException(400, 'Not open')
    if invoice.total_cents <= 0:
        raise HTTPException(400, 'Invalid total')
    # Happy path continues at left margin
    await _record_payment(db, invoice, payment)
    invoice.status = 'paid'
    await db.commit()

# Wrong
async def pay_invoice(...):
    if invoice.status == 'open':
        if invoice.total_cents > 0:
            # Happy path buried in nesting
            await _record_payment(db, invoice, payment)
```

### 4.4 Private helper functions

Functions only called within a single module are prefixed with `_`.

```python
async def _get_invoice_or_404(db: AsyncSession, invoice_id: UUID) -> Invoice:
    """Fetch invoice by ID or raise 404 if not found. Private helper."""
    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail='Invoice not found')
    return invoice
```

---

## 5 — Error Handling

### 5.1 HTTPException status codes

| Situation | Code | Message pattern |
|---|---|---|
| Resource not found | 404 | `'Invoice not found'` |
| Business rule violated | 400 | Plain English: `'Category does not belong to this brand'` |
| Not authenticated | 401 | `'Not authenticated'` (handled by auth dependency) |
| Not permitted | 403 | `'Insufficient permissions'` (handled by permission dependency) |
| Already exists | 409 | `'Device already registered to this license'` |
| Resource too large | 413 | `'File exceeds the 500KB limit'` |
| Validation error | 422 | Automatic from Pydantic |

### 5.2 Never swallow exceptions

```python
# Correct
try:
    result = await email_service.send(invite)
except EmailError as exc:
    log.error('invite.email.failed', user_id=str(user_id), error=str(exc))
    raise HTTPException(500, 'Failed to send invite email')

# Wrong
try:
    result = await email_service.send(invite)
except Exception:
    pass  # Never do this
```

---

## 6 — Database Patterns

### 6.1 Always use the ORM

Never use f-strings or string concatenation to build SQL. Use `text()` with bound parameters
only when the ORM cannot express the query.

```python
# Correct
stmt = select(Invoice).where(
    Invoice.site_id == site_id,
    Invoice.status == InvoiceStatus.PAID,
).order_by(Invoice.created_at.desc())

# Wrong — SQL injection vulnerability
sql = f"SELECT * FROM invoices WHERE site_id = '{site_id}'"
```

### 6.2 Specify columns — never SELECT *

```python
# Correct
stmt = select(
    Invoice.id,
    Invoice.invoice_number,
    Invoice.total_cents,
    Invoice.status,
).where(Invoice.site_id == site_id)

# Wrong
stmt = select(Invoice).where(Invoice.site_id == site_id)
```

### 6.3 One transaction per service call

The audit log write and the business data write happen in the same transaction. If either fails,
both roll back.

```python
async def create_product(db: AsyncSession, payload: ProductCreate, actor: User) -> Product:
    """Create a product and write the audit log in the same transaction."""
    product = Product(**payload.model_dump())
    db.add(product)
    await log_action(
        db=db, actor=actor, action=PRODUCT_CREATED,
        entity_type='product', entity_id=str(product.id),
        after_state={'name': product.name, 'price': product.price_inc_tax_cents},
    )
    await db.commit()  # Both the product and audit row commit here or both roll back
    await db.refresh(product)
    return product
```

### 6.4 Migrations

After every model change: `alembic revision --autogenerate -m "description"`  
Never run a migration against production without reviewing it first.

---

## 7 — FastAPI Patterns

### 7.1 Route handlers are thin

A route handler calls one service function and returns the result. All conditional logic,
database queries, and calculations belong in the service layer.

```python
# Correct
@router.post('/{id}/pay', response_model=InvoiceResponse)
async def pay_invoice(
    id: UUID,
    payload: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_pos_user),
) -> InvoiceResponse:
    """Record payment for an invoice."""
    return await invoice_service.pay(db, id, payload, user)

# Wrong — logic in route handler
@router.post('/{id}/pay')
async def pay_invoice(id: UUID, ...):
    invoice = await db.get(Invoice, id)
    if invoice.status != 'open':
        raise HTTPException(400, ...)
    # ...more logic in the route...
```

### 7.2 response_model on every route

Every route must declare a `response_model`. This enforces the contract with the Android app
and portal frontend, and causes FastAPI to validate and document the response shape.

### 7.3 Pagination on every list route

```python
@router.get('/products', response_model=list[ProductResponse])
async def list_products(
    site_id: UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[ProductResponse]:
    """List products for a site with pagination."""
    return await product_service.list_for_site(db, site_id, skip, limit)
```

---

## 8 — Money Arithmetic

Never use float. Use int (cents) for storage. Use `decimal.Decimal` with `ROUND_HALF_UP`
for calculations.

```python
from decimal import Decimal, ROUND_HALF_UP

# Convert user input to cents
cents = int(
    (Decimal(str(user_input)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
)

# Back-calculate inclusive tax
# tax = gross - (gross / (1 + rate))
tax_cents = int(
    (amount_cents - (Decimal(amount_cents) / (1 + rate_percent / 100)))
    .quantize(Decimal('1'), rounding=ROUND_HALF_UP)
)
```

Tax calculation rules:
- **Inclusive**: tax is already in the price. `tax = gross - (gross / (1 + rate))`
- **Exclusive**: tax is added on top. `tax = gross * rate`, `total = gross + tax`
- **Compound**: calculate GST first, then PST on the gross (not on GST-inclusive amount)
- Always use `decimal.Decimal`, never `float`

---

## 9 — Logging Patterns

### 9.1 Logger instantiation

```python
import structlog
log = structlog.get_logger(__name__)
```

### 9.2 Log call format

Pass IDs as keyword arguments — never interpolate into the message string.

```python
# Correct
log.info('invoice.voiding',
    invoice_id=str(invoice_id),
    actor_id=str(actor.id),
    site_id=str(invoice.site_id),
)

# Wrong
log.info(f'Voiding invoice {invoice_id} for user {actor.id}')
```

### 9.3 Event naming

Use dot-separated lowercase: `resource.action` or `resource.action.outcome`.

| Event | Meaning |
|---|---|
| `invoice.voiding` | Void process started |
| `invoice.void.complete` | Void succeeded |
| `invoice.void.failed` | Void failed — include `error=` kwarg |
| `auth.login.attempt` | Login attempt received |
| `auth.login.success` | Login succeeded |
| `auth.login.failed` | Login failed — do not include the reason (security) |
| `license.expiry.check` | Nightly expiry job running |
| `license.expired` | A license was expired — include `license_id=` |

### 9.4 Log levels

| Level | When to use |
|---|---|
| DEBUG | Local dev only |
| INFO | Normal operations — entry to every service function that writes |
| WARNING | Unexpected but recoverable |
| ERROR | Caught failure — always includes `error=` kwarg |
| CRITICAL | App cannot function |

### 9.5 Never log sensitive data

Never log passwords, tokens, PINs, or full request bodies.

---

## 10 — Audit Logging Rules

Every service function that modifies data must call `log_action()` from
`app/services/audit_service.py` in the same transaction as the data change.

```python
# Always use constants — never hardcode action strings
from app.constants.audit_actions import PRODUCT_CREATED

db.add(product)
await log_action(db=db, actor=actor, action=PRODUCT_CREATED, ...)
await db.commit()  # Both commit together or both roll back
```

`log_action()` must snapshot `actor_email` and `actor_name` at the time of the action.
For system jobs (nightly expiry), use `actor_type = 'system'`.

### 10.1 — `log_action()` calling convention (CRITICAL)

`log_action()` uses a bare `*` in its signature — **every parameter is keyword-only**.
Passing `db` positionally raises `TypeError` at runtime with no compile-time warning.

```python
# Correct — all keyword arguments
await log_action(
    db=db,
    actor_id=actor.id,          # uuid.UUID — NOT str(actor.id)
    actor_email=actor.email,
    actor_name=actor.name,
    action=USER_CREATED,
    entity_type="pos_user",
    entity_id=str(user.id),     # entity_id IS a str
    after_state={"name": user.name},
)

# Wrong — positional db raises TypeError
await log_action(db, actor_id=actor.id, ...)

# Wrong — str(actor.id) raises validation error (expects uuid.UUID)
await log_action(db=db, actor_id=str(actor.id), ...)

# Wrong — string actor_type raises AttributeError
await log_action(db=db, actor_type="user", ...)  # omit entirely; default is ActorType.USER
```

Key types:
- `db` → `AsyncSession` (keyword-only)
- `actor_id` → `uuid.UUID | None` (pass `actor.id` directly, never `str(actor.id)`)
- `actor_type` → `ActorType` enum — omit for user actions (defaults to `ActorType.USER`); set `ActorType.SYSTEM` for Celery jobs
- `entity_id` → `str` (convert with `str(obj.id)`)

---

## 11 — Pydantic v2 Response Schema UUID Rules

ORM models using `UUID(as_uuid=True)` return Python `uuid.UUID` objects.
Pydantic v2 with `from_attributes=True` does **not** coerce `uuid.UUID` to `str` — if the
schema field is typed `str`, serialization raises a `ValidationError` at response time.
The insert succeeds in the database but the HTTP response is a 500, so `onSuccess` never
fires on the frontend.

**Always type UUID fields as `uuid.UUID` in response schemas.** FastAPI serializes them to
JSON strings automatically.

```python
import uuid
from pydantic import BaseModel

# Correct — uuid.UUID; FastAPI serializes to string in JSON
class UserOut(BaseModel):
    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    is_active: bool
    model_config = {"from_attributes": True}

# Wrong — str field fails when ORM returns uuid.UUID object
class UserOut(BaseModel):
    id: str        # ValidationError at serialization time
    brand_id: str  # Same problem
```

This bug is silent: the DB write succeeds, the record exists in Supabase, but the frontend
receives a 500 and `onError` fires instead of `onSuccess`.
