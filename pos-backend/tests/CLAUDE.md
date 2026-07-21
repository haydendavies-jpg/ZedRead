# ZedRead — Testing Rules

## Test database

Never use the development or production database.
Use the async test engine fixture from `tests/conftest.py` — database `zedread_test`.
Never mock the database. Use real queries against the real test schema.

**Connection:** the default is the Docker Compose `postgres-test` service on **port 5433**
(this is also what CI uses). If PostgreSQL runs natively on the host instead (no Docker),
override via env var:

```bash
TEST_DATABASE_URL="postgresql+asyncpg://test:test@localhost:5432/zedread_test" python -m pytest
```

If the schema is stale after a model change, drop and recreate it:

```bash
psql -U test -h localhost -p <port> zedread_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
```

---

## Test types

| Type | What it tests | Tools |
|---|---|---|
| Unit | Individual functions in isolation: tax calculation, permission checks, price resolution | pytest, no database, fast |
| Integration | API routes end-to-end against a real test database | pytest + FastAPI TestClient + real PostgreSQL |
| Contract | API response shape matches what the Android app and portal frontend expect | pytest + Pydantic schema validation |

---

## What every route test must cover

Every new route needs integration tests for all five scenarios:

1. **Happy path** — correct input, correct auth, correct response shape and status code
2. **Auth failure** — no token → 401, wrong role → 403
3. **Invalid input** — missing required fields, wrong types → 422
4. **Business rule violation** — e.g. wrong brand's category, disabled license → 400
5. **Audit log written** — assert the correct `audit_logs` row exists with the right action

---

## Audit log assertion — required on every write test

Every test for a write operation must assert that the correct audit row was written.
This is not optional — the audit trail is a core feature.

```python
async def test_void_invoice_writes_audit_log(client, db, pos_auth_headers):
    """Voiding an invoice writes the correct audit log row."""
    invoice = await create_test_paid_invoice(db)
    await client.post(f'/invoices/{invoice.id}/void', headers=pos_auth_headers)

    audit = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(invoice.id),
            AuditLog.action == INVOICE_VOIDED,
        )
    )
    log_row = audit.scalar_one()  # Raises if 0 or 2+ rows — both are bugs
    assert log_row.actor_id == test_user.id
```

---

## Test naming

```
test_{subject}_{scenario}
test_{route}_{method}_{outcome}
test_{rule}_{when_violated}
test_{action}_{side_effect}
```

Examples:
```
test_calculate_tax_inclusive_gst_10_percent
test_invoices_post_disabled_license_returns_403
test_category_wrong_brand_returns_400
test_invoice_void_writes_audit_log
```

---

## Test file location

```
Unit tests:        tests/unit/test_{module_name}.py
Integration tests: tests/integration/test_{resource_name}_routes.py
```

---

## Standard fixtures — always use from conftest.py, never recreate them

These are the fixtures that actually exist in `tests/conftest.py` (check there for the full,
current list before writing tests — it grows with each stage):

| Fixture | Provides |
|---|---|
| `db` | `AsyncSession` that rolls back after each test, function-scoped |
| `client` | httpx `AsyncClient` against the app on the test DB, function-scoped |
| `test_group` / `test_brand` / `test_site` | Created hierarchy rows (each under the previous) |
| `test_superadmin` | A `users` row with `superadmin_role="admin"` (no tenant scope) |
| `portal_auth_headers` | `Authorization` header dict for `test_superadmin` JWT |
| `test_user` | A `users` row scoped to `test_brand` |
| `test_access_profile` / `test_manager_profile` | `access_profiles` rows for `test_brand` |
| `test_access_grant` / `test_portal_grant` / `test_brand_grant` | Grants for `test_user` |
| `pos_auth_headers` / `mgmt_auth_headers` | Auth headers for POS / management JWTs |
| `test_license` / `test_device` | License + registered device for `test_site` |
| `test_tax_category` / `test_product` | Catalog rows for `test_brand` |

---

## Test what the system does — not how it does it

Tests must survive a refactor of the internals without being rewritten.
Never patch or mock service functions to test route handlers.
Test the HTTP response and the database state — not which internal methods were called.

```python
# Correct — tests observable behaviour
async def test_invoice_paid_sets_status(client, db):
    """Invoice status is paid after successful payment."""
    invoice = await create_test_invoice(db)
    response = await client.post(
        f'/invoices/{invoice.id}/pay',
        json={'amount_cents': invoice.total_cents, 'payment_method': 'cash'},
    )
    assert response.status_code == 200
    assert response.json()['status'] == 'paid'

# Wrong — tests internal wiring, breaks on any refactor
async def test_invoice_pay_calls_service(client):
    with patch('app.services.invoice_service.pay') as mock_pay:
        await client.post('/invoices/x/pay', ...)
        mock_pay.assert_called_once()
```

---

## Unit tests

Service functions and utilities get unit tests separate from integration tests.
Pure functions (tax calculation, price resolution, permission checks) do not need a database.

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
