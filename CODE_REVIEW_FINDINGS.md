# ZedRead — Codebase Review Findings

Full-codebase pass over `pos-backend` (FastAPI) and `pos-portal` (React), plus the Markdown
documentation set. Findings are grouped by area and ordered by severity within each group.
Nothing in this document changes application behaviour — it is a review record. The accompanying
commit only refactors Markdown docs (see the final section).

Severity key: **High** = exploitable or data-integrity risk · **Medium** = real weakness, bounded
impact · **Low** = hardening / hygiene · **Efficiency** = performance/cost · **Structure** = maintainability.

---

## Security

### S1 (High) — JWTs cannot be revoked; there is no logout
`user_pos_sessions.token_jti` is written on every POS login and PIN verify
(`services/pos_auth_service.py`), and `security.py` comments it as "revocation support", but
**no code path ever checks the jti against the session table**. `resolve_access`,
`resolve_management_access`, and `resolve_catalog_access` (`utils/dependencies.py`) validate the
signature and the user/grant only. There is no logout route for any token type, and
`ended_at` is never set. Consequences:
- A leaked or stolen access token is valid until natural expiry with no way to kill it.
- Refresh tokens (`REFRESH_TOKEN_EXPIRE_DAYS`, 7–30 days) cannot be invalidated on
  compromise — deactivating the user is the only lever, and that is all-or-nothing.
- "Switch user" on a terminal leaves the previous user's session active in the DB.

Recommendation: enforce the jti. On each POS request, confirm a matching `user_pos_sessions`
row with `ended_at IS NULL`; add `POST /auth/pos/logout` and `POST /auth/portal/logout` that set
`ended_at`. For portal/mgmt refresh tokens, add a revocation list or a per-user
`token_version` claim checked on refresh.

### S2 (High) — Default `SECRET_KEY` allows forged tokens if unset
`utils/security.py` falls back to a hardcoded literal
(`"change-me-in-production-use-32-plus-chars"`) when `SECRET_KEY` is not set, and `HS256` uses
that same key to sign and verify. If the env var is ever missing in a real deployment, anyone
who knows this public default (it is in the repo) can mint valid admin tokens. Nothing fails
loudly — the app boots normally.

Recommendation: read config through a `pydantic-settings` `BaseSettings` (already a dependency)
and **fail startup** if `SECRET_KEY` is unset or equals the placeholder, outside of test/dev.
Enforce a minimum length.

### S3 (Medium) — No rate limiting / lockout on any auth endpoint
Portal login, POS login, and PIN verify (`portal_auth_service.login`, `pos_auth_service.login`,
`verify_pin`) have no attempt throttling or account lockout. PINs are 4–6 digits — brute-forcing
a known email against a site is ~10⁴–10⁶ attempts with no back-off. Failures are audited but not
acted upon. `ARCHITECTURE_MAP.md` itself notes "No rate-limiting exists."

Recommendation: add per-IP + per-account throttling (Redis is already provisioned as a Celery
broker and could back a limiter) and a lockout/back-off after N failed PIN attempts.

### S4 (Medium) — CORS `allow_headers=["*"]` with `allow_credentials=True`
`main.py` sets a single explicit origin (good) but `allow_methods=["*"]` and
`allow_headers=["*"]`. With credentialed CORS this is broader than needed. Since auth is
Bearer-token (not cookies), `allow_credentials=True` is not actually required.

Recommendation: drop `allow_credentials` (tokens ride in the `Authorization` header) or pin
`allow_headers` to `["Authorization", "Content-Type"]` and `allow_methods` to the verbs used.

### S5 (Medium) — Supabase client rebuilt on every image upload
`utils/storage.py:upload_image` calls `create_client(url, key)` on each call, and the key is the
**service-role key** (full storage authority). Per-call construction is both slow (S/E overlap
with E1) and means the powerful key is threaded through every product/logo upload request path.

Recommendation: build one module-level client at startup; consider a scoped/signed-upload
approach so the service-role key is not the credential used on the request hot path.

### S6 (Low) — Portal tokens in `localStorage`; impersonation relies on `window.open` sessionStorage copy
`pos-portal/src/api/axios.ts` stores access/refresh tokens in `localStorage`, which is readable
by any XSS on the origin. The impersonation handoff (`utils/impersonation.ts`) depends on
`window.open()` duplicating the opener's `sessionStorage` into the new tab — real browser
behaviour, but brittle and easy to regress. The per-tab isolation reasoning is sound; the storage
medium is the weak point.

Recommendation: prefer in-memory access tokens with an httpOnly refresh cookie if the backend
can set one; at minimum keep a tight CSP and treat any XSS as a full-account compromise in the
threat model.

### S7 (Low) — Email HTML built with f-strings (interpolated, unescaped)
`utils/email.py` interpolates `inviter_name`, `brand_name`, `site_name` directly into HTML.
These are trusted-ish today (staff-entered), but a name containing markup is injected verbatim
into the email body. The billing-info path already uses `string.Template.safe_substitute` and
comments the reasoning — apply the same discipline everywhere.

Recommendation: HTML-escape all interpolated values (`markupsafe.escape` / `html.escape`).

### S8 (informational) — Confirmed NOT vulnerable
- **SQL injection**: all `text()` usage (`report_service.py`) uses bound parameters; ref-number
  defaults use `server_default=text(...)` with static SQL. No f-string SQL anywhere. ✅
- **Password/PIN hashing**: argon2id via `argon2-cffi`, correct verify with `VerifyMismatchError`
  handling. ✅
- **User enumeration**: login computes all conditions before deciding and returns a vague
  message; password reset always returns success. ✅
- **Impersonation scope**: `admin_impersonation.py` restricts impersonation to master users and
  requires an Admin-role SuperAdmin. ✅
- **Container**: Dockerfile runs as non-root `appuser`. ✅

---

## Efficiency

### E1 — Per-request Supabase client construction (see S5)
`create_client` on every upload does TLS/handshake setup work per call. Build once at import.

### E2 — Sequential `await`s that could be one query or run concurrently
`resolve_management_access` and the management branch of `resolve_catalog_access`
(`utils/dependencies.py`) issue 3–4 sequential round trips per request (user → grant → profile →
scope entity → brand). On a pooled remote Postgres (Supabase transaction pooler) that is
latency-bound. Options: a single `select` with joins, or `selectinload` relationships, to collapse
the round trips. The site-scope path additionally does site→brand as two queries.

### E3 — `resolve_catalog_access` duplicates `resolve_management_access` inline
The management-token branch of `resolve_catalog_access` is a hand-copied re-implementation of
`resolve_management_access` (same queries, same checks) "to avoid double Depends() complexity".
Two copies of security-critical resolution logic will drift. Extract a shared
`_resolve_mgmt(db, payload)` helper and call it from both. (Also a Structure issue.)

### E4 — Every portal list page fetches `{ limit: 200 }` and filters client-side
Per `pos-portal/CLAUDE.md` and the pages, all filtering is client-side over a fixed 200-row
pull. Fine at current scale; will silently truncate and over-fetch as brands grow. Track a move
to server-side filtering/pagination before data volume makes 200 a real cap.

### E5 — `pool_pre_ping=True` adds a round trip per checkout
Reasonable for a pauseable Supabase project, but combined with `statement_cache_size=0`
(required by the pooler) every request pays extra latency. Acceptable given the deployment; noted
so it is a conscious trade-off, not an accident.

---

## Structure / maintainability

### T1 — Two scoped `CLAUDE.md` files were orphaned at the repo root
`app_CLAUDE.md` and `tests_CLAUDE.md` sat at the repository root, but the root `CLAUDE.md` and
tooling reference them as `app/CLAUDE.md` and `tests/CLAUDE.md`. Directory-scoped instruction
files only auto-load when they live in the directory they govern, so neither was being applied
when editing backend or test code. **Fixed in this commit** (moved into
`pos-backend/app/` and `pos-backend/tests/`).

### T2 — Documentation drift: docs describe the pre-rename model, code is post-rename
`ARCHITECTURE_MAP.md` (dated 2026-06-27) stated the rename was "not yet implemented" and used
`PortalUser`/`POSUser`/`pos_users`/`portal_users`. The code already uses `SuperAdmin`/`User`,
tables `superadmins`/`users`, routes `superadmins.py`/`users.py`, and has
`access_profile_page_permissions`. The map's own rule is "code wins" — so the map was stale
against its own contract. **Fixed in this commit** (map, README, and `CLAUDE.md` updated).

### T3 — `tests/CLAUDE.md` fixture table and port guidance were inaccurate
It listed fixtures that do not exist in `conftest.py` (`db_engine`, `test_portal_user`,
`test_pos_user`, `portal_auth_headers` naming) and hardcoded "port 5432, Docker not available" —
guidance from one specific session that contradicts `docker-compose.yml` and CI (both 5433).
**Fixed in this commit** (table reconciled with actual `conftest.py`, port guidance generalised).

### T4 — Unused dependency `bcrypt==4.2.1`
`requirements.txt` pins `bcrypt`, but hashing is entirely argon2 (`grep` finds no bcrypt import).
Dead dependency — drop it to shrink the image and attack surface. (Left as a recommendation; not
changed here to avoid touching the lockfile/build in a docs-only commit.)

### T5 — `HealthResponse(JSONResponse)` is dead code
`main.py` declares a `HealthResponse` subclass that is never used; the route returns a plain
`dict` with `response_model=dict`. Remove the unused class.

### T6 — Config read ad hoc via `os.getenv` across many modules
`security.py`, `database.py`, `email.py`, `storage.py`, and `main.py` each read env vars directly
with string defaults. `pydantic-settings` is already a dependency. A single `Settings` object
would centralise validation (enabling S2's fail-fast), remove scattered defaults, and make the
config surface auditable in one place.

### T7 — MD documentation set is large and partly redundant
~2,950 lines across 13 Markdown files, with overlapping phase/stage tables duplicated in
`README.md`, `STAGE_STATUS.md`, and `ROADMAP.md` (three copies of the same status that must be
hand-synced). The `CLAUDE.md` files were the highest-value target for reducing per-session token
cost and were tightened in this commit. A further pass could collapse the three
phase-status tables into one canonical source the others link to.

---

## What changed in this commit (docs only)
- Moved `app_CLAUDE.md` → `pos-backend/app/CLAUDE.md` and `tests_CLAUDE.md` →
  `pos-backend/tests/CLAUDE.md` so directory-scoped rules actually load (T1).
- Rewrote all three `CLAUDE.md` files for accuracy and lower token cost: removed duplicated
  absolute-rules content, fixed the fixture table against real `conftest.py`, corrected port
  guidance, and de-duplicated backend style rules against the root file (T3, T7).
- Updated `ARCHITECTURE_MAP.md`, `README.md` to match the shipped rename and Stage 15 status (T2).
- Added this findings report.

No application code was modified. The Security and Efficiency items above are recommendations for
follow-up PRs, scoped one concern at a time.
