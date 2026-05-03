# ZedRead — Testing Rules

## Test database
Never use the development or production database.
Use the async test engine fixture from tests/conftest.py — port 5433, database zedread_test.
Never mock the database. Use real queries against the real test schema.

## What every route test must cover
Every new route needs integration tests for all five of these scenarios:
1. **Happy path** — correct input, correct auth, correct response shape and status code
2. **Auth failure** — no token → 401, wrong role → 403
3. **Invalid input** — missing required fields, wrong types → 422
4. **Business rule violation** — e.g. wrong brand's category, disabled license → 400
5. **Audit log written** — assert the correct audit_logs row exists with the right action

## Audit log assertion — required on every write test
```python
audit = await db.execute(
    select(AuditLog).where(
        AuditLog.entity_id == str(entity.id),
        AuditLog.action == EXPECTED_ACTION,
    )
)
log_row = audit.scalar_one()  # Raises if 0 or 2+ rows — both are bugs
assert log_row.actor_id == expected_actor.id
```

## Test naming
```
test_{subject}_{scenario}
test_{route}_{method}_{outcome}
test_{rule}_{when_violated}
test_{action}_{side_effect}

Examples:
test_tax_calculation_inclusive_gst_10_percent
test_invoices_post_disabled_license_returns_403
test_category_wrong_brand_returns_400
test_invoice_void_writes_audit_log
```

## Test file location
- Unit tests:        tests/unit/test_{module_name}.py
- Integration tests: tests/integration/test_{resource_name}_routes.py

## Standard fixtures — always use these from conftest.py, never recreate them
| Fixture | Provides |
|---|---|
| db_engine | Async engine, session-scoped, creates/drops all tables |
| db | AsyncSession that rolls back after each test, function-scoped |
| client | FastAPI TestClient on the test DB, function-scoped |
| test_group | A created groups row |
| test_brand | A created brands row under test_group |
| test_site | A created sites row under test_brand |
| test_portal_user | An admin portal_users row |
| test_pos_user | A users row with a grant for test_brand |
| portal_auth_headers | Authorization header dict for test_portal_user JWT |
| pos_auth_headers | Authorization header dict for test_pos_user JWT |

## Test what the system does — not how it does it
Tests must survive a refactor of the internals without being rewritten.
Never patch or mock service functions to test route handlers.
Test the HTTP response and the database state — not which internal methods were called.

## Unit tests
Service functions and utilities get unit tests separate from integration tests.
Unit tests for pure functions (tax calculation, price resolution, permission checks)
do not need a database — use direct function calls with in-memory inputs.
```python
def test_calculate_tax_inclusive_10_percent():
    """Inclusive GST at 10% on $10.00 produces correct tax and subtotal."""
    tax, subtotal = calculate_tax(
        amount_cents=1000,
        rate_percent=Decimal('10.0000'),
        model='inclusive',
    )
    assert tax == 91       # 10/110 * 1000 rounded
    assert subtotal == 909 # 1000 - 91
```
