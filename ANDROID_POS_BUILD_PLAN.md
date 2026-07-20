# Android POS — Build Plan

**Purpose of this file:** the durable, cross-session record of the Android POS build plan. Pick up
here in a new session — read the Status section first, then the phase you're on.

## Status

| Phase | Area | State |
|---|---|---|
| 1 | Backend — two-step login, device pairing, license gating, register (till) sessions | ✅ Merged — [PR #92](https://github.com/haydendavies-jpg/ZedRead/pull/92) |
| 1 | Backend — register-session portal report route | 🔲 Not started |
| 1 | Portal — "POS - Site Assignment" toggle on Users edit page | 🔲 Not started |
| 1 | Portal — Register Sessions report page | 🔲 Not started |
| 1 | Android — project wiring (Retrofit/Hilt/Room/Nav) | 🔲 Not started |
| 1 | Android — Login, PIN entry, Site selector screens | 🔲 Not started |
| 1 | Android — Register (order-entry) screen, exact match | 🔲 Not started |
| 1 | Android — Modifier customise sheet, exact match | 🔲 Not started |
| 1 | Android — Payment flow (Card/Cash exact match + Voucher/Split addition) | 🔲 Not started |
| 1 | Android — Start-of-day cash-in / End-of-day cash-up screens | 🔲 Not started |
| 2 | Settings framework, idempotency, checksums, offline write-queue | 🔲 Not started |
| 3 | Menu Studio → POS integration depth (recurring scheduling, menu selector) | 🔲 Not started |
| 4 | Table maps & floor service | 🔲 Not started |

**Next up:** the remaining Phase 1 items — portal register-session report page, the Users-page toggle,
then the Android app itself (auth/PIN/site-selector screens first, since everything else depends on
having a working login).

**What Phase 1's merged backend slice actually shipped** (PR #92, on top of migration `0049` —
renumbered from `0048` during a merge-conflict resolution with main's concurrent `0048_drop_menus_table`):
- `POST /auth/pos/login` reworked into a credentials-first flow that resolves the site from the
  terminal's own device pairing (`device_token`) rather than a caller-supplied `site_id`.
- `POST /auth/pos/site-token` — new endpoint for a user with `is_pos_multi_site_enabled` ("POS - Site
  Assignment") to choose among multiple granted sites; choosing a different site re-pairs the device.
- Active-license check added to POS login (previously unchecked).
- POS access tokens now carry a `device_id` claim end-to-end; `user_pos_sessions` gained `device_id`;
  `POSAccess` exposes `.device` so any POS route can resolve which terminal is calling.
- New `register_sessions` table: open with device-local timestamp + opening cash, close with closing
  cash and a computed variance against cash takings recorded during the shift; records the full name
  of whoever opened/closed it. Invoice and refund creation are rejected with 400 until a session is
  open for the calling device.
- 785 backend tests passing (full suite) at merge time.

---

## Context

Phase 10 (Stages 25–26) of the roadmap had been scaffolding-only. The user supplied a high-fidelity
design bundle (`POS_System_Brand_Identity.zip` → `design_handoff_zedread/`: `ZedRead Register.dc.html`
+ `README.md` / `README-tables-floormap.md` / `README-menu-studio.md`) covering the front-of-house
Register app (order entry, modifier sheet, payment, Tables/floor map, top nav) in full visual and
interaction detail. **The design is already done in that file — this plan builds directly from it,
there is no separate mockup deliverable.** Screens with a reference (Register/order-entry, modifier
sheet, payment, Tables/floor map, top nav) are pixel/behavior exact matches. Screens with no
reference (Login, PIN, Site selector, Menu selector, Settings, Cash-up, Sync panel, Invoice search)
are new and get designed inline during build, reusing the bundle's shared tokens (colors, IBM Plex
Sans/Mono, Public Sans titles in the Register surface, radii/shadow/motion scale) and existing
component patterns (pill segmented controls, slide-over sheets, floating dark action bars/toasts) so
they read as authored by the same team, not bolted on.

Across several rounds the user also specified a large set of functional requirements — auth flow,
licensing, sync, menu studio integration, settings, tax, invoices/payments, register/till sessions,
table maps, and audit logging. Those are folded into the phased build below, ordered by dependency
(what has to exist on the backend before the Android screen that consumes it can be built for real,
not against a stub).

**Locked-in architecture decisions** (binding across all phases):
- A `PosDevice` stays pinned to one Site (no schema change to the 1-device-1-site model). The
  "POS - Site Assignment" flag on a User only matters when that user's grants span more than one site
  — selecting a different site in the selector **re-pairs the device** to that site for the session,
  it doesn't make the device float permanently.
- POS Settings live **per-Site, with Brand-level defaults** a site inherits until it sets its own
  override (mirrors the existing Group→Brand→Site scoping used by access profiles/licenses).
- Register/till sessions are **per-device**, not per-site — two terminals at one site run independent
  cash sessions.

---

## Phase 1 — Core sell loop

The minimum real, end-to-end path: a staff member logs in, opens the register, rings up an order, and
takes payment — matching the design file exactly wherever it defines one.

**Backend**
- ✅ Rework `POST /auth/pos/login` from its current single-call `email+password+site_id` shape into a
  two-step flow: credentials-only call resolves candidate site(s) from the device's paired site ∩ the
  user's active grants; if the user's **`is_pos_multi_site_enabled`** flag is set and more than one
  candidate exists, return `available_sites` (mirrors the portal's existing `available_grants`
  pattern) for a follow-up call that finalizes site, re-pairs the device, and issues the POS token.
  Add an active-**license** check (`License.status == 'active'` for the resolved site) before issuing
  any token — done via `POST /auth/pos/site-token`.
- ✅ Add `is_pos_multi_site_enabled` to `User`. **Still open:** expose it as an editable toggle on the
  management portal's Users edit page (labelled "POS - Site Assignment") — backend field exists,
  portal UI doesn't yet.
- No changes needed to `GET /products`/`/categories`/`/modifiers` or the existing
  `GET /pos/menu-layout?site_id=` read contract (Stage 23) — Phase 1 sells against whatever layout is
  already published; multi-menu/default-scheduling is Phase 3.
- Payment: `POST /invoices/{id}/pay` already supports `cash`/`card`/`voucher` and multiple calls for
  split — no backend change, only client-side orchestration.
- ✅ New `register_sessions` table, scoped per `PosDevice`: opened-at (device local time), opening cash
  (single bulk-value entry — the denomination-breakdown alternative is a Phase 2 setting, see below),
  closed-at, closing cash, variance, status, plus `opened_by_user_id`/`opened_by_name` and
  `closed_by_user_id`/`closed_by_name` (full-name snapshot at the time, same convention as audit rows'
  `actor_name`). `Invoice` gets a `register_session_id` FK; invoice creation is blocked until an open
  session exists for that device.
- 🔲 **Still open:** Register-session **portal report** — new read route + page (alongside
  `InvoicesPage`/`ReportsPage`) listing sessions per site/device with opening/closing cash, takings,
  variance, and who opened/closed each one. The backend data model supports this already
  (`opened_by_name`/`closed_by_name`/`variance_cents` etc. all exist on `register_sessions`) — this is
  a pure read route + portal page, no new backend logic.

**Android** (none of this started yet)
- Project wiring: Retrofit client, Hilt DI modules, Room DB, Compose nav graph (existing Stage 25
  scaffolding, filled in for real).
- **Login** screen (email + password, ZedRead wordmark, Public Sans 700 titles matching the Register
  surface's type treatment). Calls `POST /auth/pos/login` with `{email, password, device_token}`.
- **PIN entry** screen (numeric keypad, current-user context).
- **Site selector** screen — shown only when login returns `available_sites`; selecting a non-paired
  site shows a brief inline notice that this re-pairs the device for the session. Calls
  `POST /auth/pos/site-token` with the chosen `site_id`.
- **Register / order-entry screen** — exact match to `ZedRead Register.dc.html`: header, category
  rail, product grid (text-only + with-image tiles), order pane (ticket header, order-type segmented
  control, line list with qty stepper, totals footer, Hold/Pay).
- **Modifier customise sheet** — exact match (slide-over, group blocks, qty stepper, live total).
- **Payment flow** — exact match for Card/Cash tabs and the Choosing/Done states, **plus one flagged
  addition**: a third **Voucher** tab (reference-code input, same visual language as Card) and a
  **Split** toggle on Cash/Card (partial amount + "Add another payment" keeps the modal open with a
  running "remaining due") — since the mockup predates the voucher/split backend capability.
- Basic online invoice creation (no offline queue yet — that's Phase 2). Must call
  `GET /register-sessions/current` on launch/resume and route to cash-in if null before allowing a
  sale — `POST /invoices` returns 400 otherwise.
- **Start-of-day cash-in**: bulk-value entry (denomination-breakdown variant added in Phase 2 once the
  settings framework can toggle it); blocks Register access with an "enter start-of-day cash to
  continue" gate until a session is open. Calls `POST /register-sessions/open`.
- **End-of-day cash-up**: bulk-value entry compared against expected takings, variance shown (the
  hide-variance option is a Phase 2 setting); confirm-close. A "Cash Up" entry point in the
  account/nav menu. Calls `POST /register-sessions/{id}/close`.

**Backend API reference for Phase 1 Android work** (all merged, live on `main`):
- `POST /auth/pos/login` `{email, password, device_token}` → token, or `{available_sites: [...]}`.
- `POST /auth/pos/site-token` `{email, password, device_token, site_id}` → token.
- `GET /register-sessions/current` → open session for this device, or `null`.
- `POST /register-sessions/open` `{opened_at, opening_cash_cents}` → session.
- `POST /register-sessions/{session_id}/close` `{closed_at, closing_cash_cents}` → session with
  computed `expected_cash_cents`/`variance_cents`.
- `POST /invoices` — now requires an open register session for the device (400 otherwise); response
  includes `register_session_id`.

---

## Phase 2 — Operational continuity: till sessions, settings, offline sync

Makes the app usable for a real shift, not just a demo: cash accountability, configurable behavior,
and the guarantee that no sale is ever lost to a bad connection.

**Backend**
- Settings framework: new `site_settings`/`brand_settings` (or one table with nullable `site_id` and
  brand-level fallback resolved in the service layer), typed values (boolean / datetime / single-select
  / multi-select), exposed via a POS read endpoint and a new portal Settings management page. **Must
  be searchable** (by name/label/category) on both surfaces as the settings catalog grows. Ship with
  at least the two settings Phase 1's cash-in/cash-up screens are waiting on (cash-in mode:
  denomination vs bulk; hide-variance-on-close) so the pattern is proven end to end and those screens
  become configurable.
- **Idempotency**: a client-generated key (UUID minted at creation time on-device) accepted by
  `POST /invoices`, its payment calls, and the register-session create/close routes, deduped
  server-side via a new nullable unique `client_ref` column on `invoices` and `register_sessions` — a
  retried offline write must not create a duplicate if an earlier attempt actually landed but the
  device never saw the response.
- **Checksum verification**: `invoices` and `register_sessions` each carry a checksum (SHA-256 over
  the canonical serialized payload — line items/totals/payments for an invoice; counts/totals for a
  session) computed on-device at creation and re-verified server-side on sync; a mismatch is rejected
  and surfaced as a sync error rather than silently accepted. The sync response echoes the server's own
  computed checksum so the device can confirm the stored record matches what it sent.
- New audit action constants for till open/close (already added — `REGISTER_SESSION_OPENED`/
  `REGISTER_SESSION_CLOSED`) and for sync completion (not yet added; no new logging mechanism —
  existing `log_action()` wraps these service calls same as everything else).

**Android**
- **Settings** screen: searchable list of boolean/datetime/dropdown/multiselect rows.
- Extend Phase 1's **start-of-day cash-in** / **end-of-day cash-up** screens: add the
  denomination-grid variant (toggled by the cash-in-mode setting) alongside the existing bulk-value
  entry, and make the variance line hideable per the hide-variance setting.
- **Offline write-queue**: local Room outbox for pending invoices and register-session events (each
  tagged with its idempotency key and checksum), drained by a WorkManager job constrained to
  `NetworkType.CONNECTED`, retrying with backoff but **never expiring or discarding** an item — matches
  the explicit "hold indefinitely until a connection is established" requirement. On reconnect the
  worker runs a **cycling resync pass**; a manual **"Sync now"** action forces an immediate pass.
  Till/register-session running totals count queued-but-unsynced invoices immediately, not after the
  portal round-trip.
- **Offline / pending-sync indicator**: persistent, unobtrusive status badge ("Offline · N pending" /
  "Synced") visible from Register at all times — never a blocking modal, staff keep selling while
  offline. Tapping it opens a **sync panel**: per-item status, a **plain-language** failure reason
  when something genuinely fails (checksum mismatch, server rejection — worded for a non-technical
  cashier, not an error code), and the manual "Sync now" action.
- **Invoice search/history**: filterable (date range, status, payment method) list reading the local
  Room cache so it works offline; results show synced/pending state per item. Nav entry point
  alongside Cash Up/Settings.

---

## Phase 3 — Menu Studio → POS integration depth

Moves from "one published layout" to the full multi-menu, scheduled-default behavior the user
described.

**Backend**
- `menus` (the standalone entity) was **removed entirely** post-Phase-1 as redundant (see
  `STAGE_STATUS.md` "Menus tab removal") — its draft/schedule/publish lifecycle already lives directly
  on `menu_layouts`. This phase's "recurring daypart scheduling + default menu" work now targets
  `menu_layouts`' site-assignment model instead of the removed `menus` table — re-scope against
  current code before starting, this plan predates that removal.
- Add recurring **daypart** scheduling (`is_all_day`/`start_time`/`end_time`/`active_days`, which
  `menu_layouts` already has) at the site-assignment level, plus an **`is_default`** flag per site
  assignment so exactly one layout is the scheduled/default choice for a given site at a given time.
- Portal: an **assign-to-site** selector (which layouts are available to which sites, and which is
  default) — `menu_layouts` today publish per brand/site scope already; confirm what's actually
  missing before building.

**Android**
- **Menu selector** control (Register header, near the category rail): lets staff switch among
  published menu layouts granted to the site; visually distinguishes the schedule-active default from
  a manually overridden choice; after a completed transaction the app reverts to whichever layout is
  scheduled-active at that moment.

---

## Phase 4 — Table maps & floor service

New scope beyond the original Stage 25/26 description (the user brought the design bundle's Tables
screen into scope after initially being told it was excluded). Table maps are **authored on the
portal**; the device only renders published ones and drives live status.

**Backend**
- New `table_maps` / `table_map_shapes` tables: position, size, shape kind (table shapes — stool/round/
  rect — and **non-table decorative shapes** — zones, bar counter, entrance marker, walls), lock state,
  per-map publish flag, multiple maps per site (generalized "floor" concept).
- Live status layer: `dining_tables`/`table_sessions` (status/covers/seated-at/server/merge-partner),
  matching `README-tables-floormap.md`'s status model.
- `GET /pos/table-map?site_id=` read contract, mirroring the existing `GET /pos/menu-layout?site_id=`
  pattern, plus status-mutation routes (seat/order/bill/merge/clear).
- `Invoice` gets a nullable `table_session_id` FK — the mockup's "Open order →" attaches a Register
  order to the selected table's session.
- Table-map/session sync joins the same idempotency/checksum/offline-queue treatment as Phase 2's
  invoices and register sessions.

**Portal**
- Floor-map editor page: drag-and-drop shape placement, resizable, snap-to-grid with a **lockable**
  grid, a **scalable** canvas, multiple map indices per site, publish/unpublish per map. Architecturally
  this reuses the existing Menu Studio POS Layout grid editor pattern (`menu_builder_service.py` /
  `MenuBuilderPage.tsx` — pointer-based select/drag/resize, publish/unpublish, multiple layouts)
  rather than inventing a new one, styled with the portal's already-adopted design system — no new
  mockup work needed for this page.

**Android**
- **Tables / Floor Map screen + persistent top nav** — exact match to `README-tables-floormap.md`:
  floor tabs, map canvas with zone backdrops and table tiles, status legend, selection bar (Merge /
  Open order / close), the full merge-flow interaction, reservation/merge/total badges. "Open order →"
  hands off into Register scoped to that table's session.

**Online** (delivery/pickup queue) stays excluded — no backend route or requirement for it exists
anywhere in this project's scope; it's only present in the reference bundle as shared top-nav context.
Revisit only if online ordering is ever explicitly scoped in.

---

## Verification (per phase)

Each phase should be run and exercised end-to-end on a real device/emulator before moving on — not
just unit-tested: Phase 1's login→register→payment loop; Phase 2's cash-in→sale→cash-up cycle plus a
forced-offline sale that later syncs; Phase 3's menu switch and scheduled-default reversion; Phase 4's
table select→merge→open-order flow. Backend changes each get integration tests per this repo's
existing testing rules (`pos-backend/tests/CLAUDE.md`), including an audit-log assertion for every new
write path.

**How Phase 1's backend slice was verified** (for reference on future slices): local Postgres 16
instance, migrations applied clean from `0001` through head, full backend suite run
(`TEST_DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/zedread_test python -m pytest
tests/ -q`) — 785 passed. Portal build verified with `npm run build` in `pos-portal/`. CI (`Backend
tests` + `Portal build` GitHub Actions jobs) green on the merge commit before merging.
