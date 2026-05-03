# ZedRead — Application Code Rules

## Type hints
Every function parameter and return value must have a type hint. No exceptions.
```python
# Correct
async def get_invoice(invoice_id: UUID, db: AsyncSession) -> InvoiceResponse:

# Wrong
async def get_invoice(invoice_id, db):
```

## Docstrings
Every function, class, and module must have a docstring using Args / Returns / Raises format.
```python
async def calculate_tax(amount_cents: int, rate_percent: Decimal, model: str) -> tuple[int, int]:
    """
    Calculate tax for a line item.

    Args:
        amount_cents: Pre-tax amount in smallest currency unit.
        rate_percent: Tax rate as a percentage e.g. Decimal('10.0000').
        model: 'inclusive' or 'exclusive'.

    Returns:
        Tuple of (tax_cents, subtotal_cents).

    Raises:
        ValueError: If model is not 'inclusive' or 'exclusive'.
    """
```

## Inline comments
Add a comment on any line that is not immediately obvious. Always comment:
- Money arithmetic
- Non-obvious conditionals
- Magic numbers (use a named constant instead)
- Non-obvious database filters or joins
```python
# Back-calculate tax from gross: tax = gross - (gross / (1 + rate))
tax_cents = round(amount_cents - (amount_cents / (1 + rate_percent / 100)))
```

## Naming
| Thing | Convention | Example |
|---|---|---|
| Files/modules | snake_case | invoice_service.py |
| Classes | PascalCase | InvoiceService, TaxCategory |
| Functions | snake_case | calculate_tax(), get_invoice_or_404() |
| Constants | UPPER_SNAKE_CASE | INVOICE_PAID, MAX_PIN_LENGTH |
| Pydantic schemas | PascalCase + suffix | InvoiceCreate, InvoiceResponse |
| SQLAlchemy models | PascalCase singular | Invoice, LineItem (not Invoices) |
| DB tables | snake_case plural | invoices, invoice_line_items |
| DB columns | snake_case | created_at, brand_id |
| Monetary columns | suffix _cents | price_inc_tax_cents, amount_cents |
| Boolean columns | is_ or has_ prefix | is_active, is_taxable, has_variants |
| Foreign keys | table_singular + _id | brand_id, site_id, actor_id |
| Private helpers | _ prefix | _get_invoice_or_404(), _apply_void() |

## Money arithmetic
Never use float. Use int (cents) for storage and arithmetic. Use Decimal with ROUND_HALF_UP
when converting user input.
```python
from decimal import Decimal, ROUND_HALF_UP
cents = int((Decimal(str(user_input)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
```

## Function design
- Max 40 lines per function — split if longer
- Return early rather than nesting the happy path
- One responsibility per function — if the docstring says "and", consider splitting
- Private helpers (underscore prefix) for logic only used within the same module

## FastAPI route rules
- Route handlers call one service function and return the result — nothing else
- Every route declares a response_model
- Every list route supports pagination: skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)
- HTTP status codes: 201 for create, 200 for actions, 400 for business rule violation,
  401 unauthenticated, 403 forbidden, 404 not found, 409 conflict, 413 too large, 422 validation

## Error handling
- Raise HTTPException from services with a plain English detail message
- Never catch an exception and do nothing — log at ERROR and re-raise
```python
except EmailError as exc:
    log.error('invite.email.failed', user_id=str(user_id), error=str(exc))
    raise HTTPException(500, 'Failed to send invite email')
```

## Database rules
- Always use SQLAlchemy ORM — never f-string SQL
- Always specify columns — never select(Model) when you only need a few fields
- Always specify columns: SELECT id, name, status — never SELECT *
- After every model change: alembic revision --autogenerate -m "description"

## Logging rules
- Module-level logger: log = structlog.get_logger(__name__)
- Log INFO at entry to every service function that writes to the DB
- Log event names as dot-separated lowercase: invoice.voiding, auth.login.failed
- Pass IDs as keyword args — never interpolate into the message string
- Never log passwords, tokens, PINs, or full request bodies
- Log levels: DEBUG (local dev only), INFO (normal ops), WARNING (unexpected),
  ERROR (caught failures), CRITICAL (app cannot function)

## Audit logging rules
- Every service function that modifies data calls log_action() from app/services/audit_service.py
- Always use constants from app/constants/audit_actions.py — never hardcode action strings
- The audit write must be in the same db.add() / await db.commit() transaction as the data change
```python
db.add(product)
await log_action(db=db, actor=actor, action=PRODUCT_CREATED, ...)
await db.commit()  # Both commit together or both roll back
```
