# Codebase Review — Remaining Backlog

Tracks the open items from the `2026-07` codebase review (`CODE_REVIEW_FINDINGS.md`). The security
findings and the two low-risk cleanups were shipped; what's left is captured here to be picked up in a
future revision. IDs (S#, E#, T#) map to sections in `CODE_REVIEW_FINDINGS.md`.

## Shipped (for reference — do not redo)
| Item | Finding | PR |
|---|---|---|
| SECRET_KEY fail-fast on prod boot | S2 | #47 |
| POS token revocation (jti + `/auth/pos/logout`) | S1 | #48 |
| Portal/mgmt token revocation (`token_version`) | S1 remainder | #52 |
| Per-account login/PIN rate limiting + CORS tightening | S3 | #53 |
| Supabase client built once (not per upload) | S5/E1 | #51 |
| Drop unused `bcrypt` dep + dead `HealthResponse` | T4/T5 | #50 |

## Open — security / hardening
- [ ] **Distributed rate limiter (S3 follow-up).** The limiter in `app/utils/rate_limit.py` is
      in-process, so each API replica counts independently. Move to a shared store (Redis is already
      provisioned as the Celery broker) when running more than one replica. `check_rate_limit(key,
      max, window)` is store-agnostic — swap the backing dict without touching call sites.
- [ ] **Scope the Supabase upload credential (S5 follow-up).** `upload_image` uses the service-role
      key (full storage authority) on the request path. Prefer scoped/signed uploads or a
      least-privilege key so a compromise of the API process can't touch arbitrary storage.
- [ ] **Per-session management logout.** Portal/mgmt tokens are revocable via `token_version`
      (logout-everywhere / password change). A selective single-session logout for management users
      would need per-session tracking (like the POS `user_pos_sessions` model).

## Open — efficiency
- [ ] **E2 — collapse auth resolution round-trips.** `resolve_management_access` and the management
      branch of `resolve_catalog_access` (`app/utils/dependencies.py`) do 3–4 sequential queries
      (user → grant → profile → scope entity → brand) per request. Use joins or `selectinload` to cut
      the round trips on the pooled remote DB.
- [ ] **E4 — server-side list filtering.** Portal list pages fetch `{ limit: 200 }` and filter
      client-side (`pos-portal/CLAUDE.md`). Move filtering/pagination server-side before data volume
      makes 200 a real cap.
- [ ] **E5 — `pool_pre_ping` cost (noted, not necessarily actionable).** Combined with
      `statement_cache_size=0` (required by the Supabase pooler) it adds latency per checkout —
      a conscious trade-off for a pausable DB; revisit if it shows up in latency budgets.
- [ ] **E3 — already addressed conceptually.** `resolve_catalog_access` still hand-duplicates
      `resolve_management_access`; extract a shared `_resolve_mgmt(db, payload)` helper to prevent
      drift (the two now also share the `token_version` check added in #52).

## Open — structure / docs
- [ ] **T6 — centralize config.** `os.getenv` reads are scattered across `security.py`, `database.py`,
      `email.py`, `storage.py`, `rate_limit.py`, `main.py`. A single `pydantic-settings` `Settings`
      object would centralize validation (and could host the SECRET_KEY fail-fast from #47).
- [ ] **T7 — de-duplicate status tables.** Phase/stage status is duplicated across `README.md`,
      `STAGE_STATUS.md`, and `ROADMAP.md` and must be hand-synced. Pick one canonical source and have
      the others link to it.

_See `CODE_REVIEW_FINDINGS.md` for the full write-up and the "confirmed clean" list._
