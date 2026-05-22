# ZedRead POS — Architecture Decision Records

ADRs capture significant choices made during the design and build of this system. They are numbered in the rough order decisions were made. "Superseded" ADRs are kept for historical context.

---

## ADR-001 — Store all monetary values as integer cents (BIGINT)

**Status:** Accepted  
**Stage:** 1 (established before any tables were created)

### Context
POS systems perform frequent arithmetic on prices: multiply by quantity, sum lines, extract tax from inclusive prices, apply percentage discounts. Floating-point types (FLOAT, DOUBLE, DECIMAL with floating-point backing) introduce rounding errors that accumulate across a transaction. A $0.001 error per line × 50 lines per invoice × 10,000 invoices per month becomes a material discrepancy.

### Decision
Every monetary column is stored as `BIGINT` (integer cents). `$12.99` is stored as `1299`. Column names **must** end in `_cents`. Python `Decimal` with `ROUND_HALF_UP` is used for any intermediate arithmetic.

### Consequences
- **Positive:** No floating-point rounding errors. Integer arithmetic is deterministic and fast.
- **Positive:** Column naming convention makes monetary columns self-documenting.
- **Negative:** Division requires care (e.g. `1299 ÷ 2 = 649.5 → 650` after rounding) — callers must be aware.
- **Negative:** Humans reading raw DB values must mentally divide by 100.

---

## ADR-002 — Three-level tenant hierarchy (Group → Brand → Site)

**Status:** Accepted  
**Stage:** 1

### Context
The platform must serve multiple independent businesses (resellers/franchises) each with multiple brands, and each brand may have multiple physical locations. The data isolation boundary and permission scoping need to be clear and enforceable.

### Decision
Three hierarchy levels: **Group** (reseller or top-level owner) → **Brand** (business concept, e.g. "Burger Barn") → **Site** (physical location). The product catalog is scoped at the Brand level because a chain shares its menu across locations. Invoices and devices are scoped at the Site level because a transaction belongs to a specific location.

### Consequences
- **Positive:** Clean separation of concerns — catalog management at brand, transactions at site.
- **Positive:** A user's permission grant can target any level, enabling flexible access control.
- **Negative:** Three-table joins are required for many queries that need full context.
- **Negative:** Hierarchy status changes (suspend group) need to cascade intent to child entities — currently handled in service layer, not via DB cascades.

---

## ADR-003 — Snapshot product/price/tax data onto invoice line items

**Status:** Accepted  
**Stage:** 10

### Context
POS systems have a strict requirement: a paid invoice must always reflect exactly what was sold at the time of the sale. If a cashier sold a burger for $10 in January and the price changes to $12 in March, the January invoice must still show $10. Products can also be deleted.

### Decision
When an `InvoiceLineItem` is created, `product_name`, `unit_price_cents`, `tax_category_name`, `tax_rate_percent`, and `tax_model` are **copied onto the row**. These are stored as plain columns, not foreign keys. The `product_id` FK is retained only as an optional reporting hint (`SET NULL` on product delete).

### Consequences
- **Positive:** Historical invoices are immutable and correct regardless of future catalog changes.
- **Positive:** Deleting a product does not corrupt old invoices.
- **Negative:** Snapshot columns duplicate data present in the products table.
- **Negative:** Developers must never update snapshot columns after creation — this is enforced by code convention and code review, not a DB constraint.

---

## ADR-004 — Audit every write in the same database transaction

**Status:** Accepted  
**Stage:** 1

### Context
For compliance and debugging, every state-changing operation must be traceable. Audit rows written outside the business transaction can be lost if the business write fails or if the audit write fails independently.

### Decision
Every service function that changes state calls `log_action()` (in `app/services/audit_service.py`) inside the same `AsyncSession` as the business write. Both rows are committed (or rolled back) atomically.

### Consequences
- **Positive:** Audit trail is always consistent with business data.
- **Positive:** `before_state`/`after_state` JSONB captures the full entity snapshot for debugging.
- **Negative:** Slight increase in transaction size (one extra INSERT per write).
- **Negative:** Service functions must always have access to the session object to call `log_action()`.

---

## ADR-005 — Two separate authentication flows (Portal vs POS)

**Status:** Accepted  
**Stage:** 2 (portal) / 7 (POS)

### Context
The portal (web browser) and POS terminal (Android touchscreen) have fundamentally different UX constraints and security models. A portal admin authenticates once per session via a browser. A POS cashier may share a terminal with five colleagues and needs to switch users in under three seconds.

### Decision
- **Portal:** Email + password (Argon2) → JWT with role claim. Standard web auth pattern.
- **POS:** Email + password on first login sets a 4–6 digit PIN. Subsequent logins use email + PIN only. PIN is verified against an Argon2 hash in `user_pins`. The device must have an active `device_token` tied to an active license.

These are separate endpoints, separate JWT claims shapes, and separate auth dependencies.

### Consequences
- **Positive:** Fast user switching at the terminal without typing a full password.
- **Positive:** Clear separation of concerns between portal and POS auth logic.
- **Negative:** Two auth flows to maintain and test.
- **Negative:** PIN security is weaker than a full password — mitigated by device binding and license checks.

---

## ADR-006 — Access control via named profiles + scoped grants

**Status:** Accepted  
**Stage:** 5 (profiles) / 7 (grants extended), refined in Stage 13

### Context
Different staff roles at a POS terminal need different permissions (Manager can void invoices; Cashier cannot). These permission sets need to be configurable per brand without hardcoding a fixed list of roles in the application.

### Decision
- An **AccessProfile** is a named permission tier belonging to a brand (e.g. "Manager"). Four system profiles are seeded automatically when a brand is created and cannot be deleted. Custom profiles can be added.
- A **UserAccessGrant** links a POS user to a scope (site/brand/group) using a specific profile. One user can hold multiple grants. The first grant is marked `is_default` for the default site at login.
- `backend_role` on a grant controls portal management access (`admin` / `users` / `reporting` / NULL).

### Consequences
- **Positive:** Permissions are flexible and brand-configurable.
- **Positive:** One user can have different roles at different sites (Cashier at Site A, Manager at Site B).
- **Negative:** More complex than a simple role field on the user row.
- **Negative:** The scope FK consistency check constraint (ensuring exactly one of `site_id`/`brand_id`/`group_id` is set) must be maintained carefully.

---

## ADR-007 — Multiple Payment rows per invoice (split payment support)

**Status:** Accepted  
**Stage:** 10

### Context
Many POS transactions involve split payments — for example, a customer pays $20 cash and the remaining $5.50 by card. A single `payment_method` and `amount` column on the invoice cannot represent this.

### Decision
Payments are stored as a child table `payments` with one row per payment event. The invoice transitions to `paid` when `SUM(payments.amount_cents) >= invoices.total_cents`. Each payment row records its own `method`, `amount_cents`, and optional `reference` (card terminal reference or voucher code).

### Consequences
- **Positive:** Split payments are represented accurately.
- **Positive:** Partial payments are naturally modelled — the invoice stays `open` until fully covered.
- **Positive:** Detailed payment method reporting is trivial (aggregate by `method`).
- **Negative:** Determining payment status requires a sum query rather than reading a single column.

---

## ADR-008 — Device binding: unique `device_token` tied to license

**Status:** Accepted  
**Stage:** 4

### Context
The system must be able to deactivate POS terminals when a license expires or is cancelled. It must also prevent the same physical device from being registered twice.

### Decision
Each Android terminal registers with a `device_token` (a string it generates and stores locally). The token is enforced `UNIQUE` at the DB level — duplicate registration returns HTTP 409. The `PosDevice` row has a `license_id` FK; when the Celery job expires a license, all associated devices are considered inactive.

### Consequences
- **Positive:** Hard deactivation of terminals is possible by expiring/disabling the license.
- **Positive:** Double-registration is caught at the DB level, not just application code.
- **Negative:** If a device's storage is wiped, it must re-register with a new token — creating a new `pos_devices` row (the old one stays as a deactivated record).

---

## ADR-009 — Async SQLAlchemy for all database access

**Status:** Accepted  
**Stage:** 1

### Context
A POS backend with many concurrent terminal requests benefits from non-blocking I/O. Python's `asyncio` with `asyncpg` allows the event loop to handle other requests while waiting for database results.

### Decision
Use `SQLAlchemy 2.0` with `asyncpg` and `AsyncSession` throughout. All service functions and route handlers are `async def`. The session factory yields `AsyncSession` per request via FastAPI dependency injection.

### Consequences
- **Positive:** Better throughput under concurrent load.
- **Positive:** Consistent async/await pattern throughout the codebase.
- **Negative:** Every database interaction requires `.await` — missing it causes silent bugs.
- **Negative:** Async SQLAlchemy session management is more complex (lazy loading is disabled; relationships must be explicitly joined or loaded with `selectinload`).

---

## ADR-010 — PostgreSQL views for reporting (not ORM models)

**Status:** Accepted  
**Stage:** 11

### Context
Eight reporting queries aggregate invoice, line item, tax breakdown, and payment data across potentially millions of rows. Building these as ORM queries would result in N+1 loads or complex join chains that are hard to optimise.

### Decision
Create eight PostgreSQL views (`vw_*`) via `op.execute()` in Alembic migration `0010_create_reporting_views.py`. The reporting service executes `SELECT * FROM vw_*` with scope filters rather than constructing ORM joins.

### Consequences
- **Positive:** Database-level optimisation (query planner can use indexes across the view).
- **Positive:** Reporting logic is expressed in SQL where it is most readable.
- **Negative:** Views are not in the SQLAlchemy model registry — schema changes require manual view updates alongside model changes.
- **Negative:** Views must be dropped and recreated in migrations if their underlying tables change.

---

## ADR-011 — structlog for structured JSON logging with request correlation

**Status:** Accepted  
**Stage:** 1

### Context
Production log analysis requires machine-parseable log lines that can be correlated across the lifecycle of a single HTTP request. Plain-text logging makes this impractical at scale.

### Decision
Use `structlog` with a JSON renderer in production (`LOG_FORMAT=json`) and a ColourRenderer in development. Request ID middleware assigns a UUID to every request and binds it to the structlog context so all log lines within a request carry the same `request_id`. This value is also written to `audit_logs.request_id`.

### Consequences
- **Positive:** Every log line can be correlated to its HTTP request via `request_id`.
- **Positive:** Grafana Loki can parse and index fields from the JSON output.
- **Negative:** Developers must use `structlog.get_logger()` rather than the stdlib `logging` module.

---

## ADR-012 — Celery + Redis for background jobs (license expiry)

**Status:** Accepted  
**Stage:** 4

### Context
License expiry must run on a schedule (nightly) without blocking HTTP request handling. It also needs to write audit rows using `actor_type='system'`, matching the same audit pattern as user-triggered changes.

### Decision
Use Celery with Redis as the broker. The nightly expiry task runs as a periodic Celery beat task, uses a dedicated `AsyncSession`, and calls the same `log_action()` service with `actor_type=ActorType.SYSTEM`.

### Consequences
- **Positive:** Expiry is decoupled from request handling; HTTP latency is unaffected.
- **Positive:** System-initiated audit rows are indistinguishable in structure from user-initiated ones.
- **Negative:** Adds Redis as a required infrastructure dependency.
- **Negative:** Celery worker health must be monitored separately from the API process.
