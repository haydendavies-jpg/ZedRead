# Android POS — Build Plan

**Purpose of this file:** the durable, cross-session record of the Android POS build plan. Pick up
here in a new session — read the Status section first, then the phase you're on.

## Status

| Phase | Area | State |
|---|---|---|
| 1 | Backend — two-step login, device pairing, license gating, register (till) sessions | ✅ Merged — [PR #92](https://github.com/haydendavies-jpg/ZedRead/pull/92) |
| 1 | Backend — register-session portal report route | ✅ Done |
| 1 | Portal — "POS - Site Assignment" toggle on Users edit page | ✅ Done |
| 1 | Portal — Register Sessions report page | ✅ Done |
| 1 | Android — project wiring (Retrofit/Hilt/Room/Nav) | ✅ Done |
| 1 | Android — Login, Site selector, PIN set/switch-user screens (self-service device claiming — no Device Setup screen) | ✅ Done |
| 1 | Android — Register-session gate + start-of-day cash-in screen | 🔶 Partial — end-of-day cash-up not started |
| 1 | Android — functional (non-exact-match) sell loop: browse → cart → pay | ✅ Done — see below |
| 1 | Android — Register (order-entry) screen, exact match to design bundle | 🔲 Not started — functional but generic placeholder UI today |
| 1 | Android — Modifier customise sheet, exact match | 🔲 Not started |
| 1 | Android — Payment flow, exact match + Voucher tab/Split toggle | 🔶 Partial — Cash/Card + split work functionally, not styled; no Voucher tab |
| 2 | Settings framework, idempotency, checksums, offline write-queue | 🔲 Not started |
| 3 | Menu Studio → POS integration depth (recurring scheduling, menu selector) | 🔲 Not started |
| 4 | Table maps & floor service | 🔲 Not started |

**Next up:** the portal side of Phase 1 is complete, and the Android app now has a functional
end-to-end sell loop (device setup → login → till open → browse → cart → pay), verified by manual
code review only (see "not verified against a real build" below — still true). What's left in Phase 1
is purely visual/UX: the exact-match Register screen and modifier sheet from the design bundle, the
Voucher tab + styled Split flow, and end-of-day cash-up.

**What the Android auth slice actually shipped** (this session — no PR yet, see branch
`claude/session-a61ycb`): the Stage 25 Android scaffolding predated PR #92's backend rework and called
endpoints that no longer exist (`/auth/pos/token`, `/auth/pos/refresh`) with the wrong request/response
shapes (no `device_token`, a `valid`/`must_reset` PIN-verify shape the real 401-on-failure endpoint
doesn't have). Rewrote the auth-adjacent Retrofit/Hilt/Room layer and screens to match the real,
already-merged contract:
- `ApiModels.kt`/`PosApiService.kt` now mirror `app/schemas/pos_auth.py` and
  `app/schemas/register_session.py` exactly — two-step device-paired login
  (`POST /auth/pos/login` → token or `available_sites` → `POST /auth/pos/site-token`), PIN
  set/verify, and the three `/register-sessions/*` routes. No refresh-token endpoint exists in the
  backend, so that concept was dropped rather than left half-wired.
- New **Device Setup** screen + `TokenStore` support for pairing: `device_token` (issued by a portal
  admin via `POST /pos-devices`, not the operator's own credentials) turned out to be a hard
  prerequisite for the login screen to even call the API, and wasn't accounted for in the original
  scaffolding or screen list — added as the minimum needed to make Login functional, not scope creep.
  `TokenStore` now also separates device pairing from the operator session (`clearSession()` keeps
  the pairing on logout, matching the "device stays pinned" architecture decision above).
  `POST /pos-devices` itself had no portal UI at all (API-only, first tested via curl/Swagger) — a
  follow-up added **`PosDevicesPage.tsx`** (new admin-portal page at `/pos-devices`, `SUPER_ADMIN_NAV`)
  to register/deregister terminals: site + license (filtered per selected site) + device name + a
  device token field with a "Generate" button (random 32-char hex, still freely editable) and
  click-to-copy so the value can be pasted straight into the app's Device Setup screen.
- Corrected the actual login flow: the backend issues a token directly from
  `login()`/`select_site()` with no PIN step in between — `is_pin_reset_required` on that response
  (not a separate PIN check) is what decides whether **PinSetScreen** appears next. The scaffolding's
  separate post-login "PinEntryScreen" had no real trigger under the actual contract (PIN verify is
  unauthenticated and switch-user-shaped, keyed by email) — deleted it and folded its job into
  **SwitchUserScreen** (now takes an email field, shown as "PIN entry" doubling as switch-user per the
  plan's screen list), rather than ship a second, functionally duplicate screen.
  `RegisterGateScreen`/`CashInScreen` (new) implement the "must call `GET /register-sessions/current`
  on launch and route to cash-in if null" requirement below.
- **Not verified against a real build**: this sandbox cannot reach Google's Maven repo (same class of
  network-policy gap as the backend's unreachable Postgres), so the Android Gradle Plugin itself can't
  be resolved here — `gradle :app:compileDebugKotlin` fails at plugin resolution, not at any Kotlin
  source. Checked manually instead: every renamed/removed API symbol was grepped for stale call sites,
  and every screen/nav route pairing was cross-checked. Needs a real compile + emulator run before
  merging with confidence — flagging rather than claiming a build that didn't happen.

**What the functional sell-loop slice shipped** (same session, on top of the auth slice above): the
Catalog/Cart/Payment scaffolding had its own contract drift plus a load-bearing bug, both fixed —
- `ApiModels.kt`/`PosApiService.kt`: `POST /invoices` takes no request body at all (site/brand/
  register-session all resolve server-side from the caller's POS token) — the scaffolding was sending
  a `{site_id, invoice_type}` body the route doesn't declare a parameter for. `AddLineItemRequest` had
  a `modifier_ids` field the real endpoint doesn't accept — modifiers attach one at a time via a
  separate `POST .../line-items/{id}/modifiers` call, which nothing calls yet (no modifier-picking UI
  exists). Both fixed to mirror the inline request/response models in
  `app/services/invoice_service.py` (there is no separate `schemas/invoice.py`).
- **The bug**: tapping a product called `startInvoice()`, which created an *empty* draft invoice and
  immediately navigated to Cart — the tapped product was never added as a line item, so Cart always
  rendered empty. Separately, Cart and Payment each instantiated their own fresh `hiltViewModel()`,
  and since there's no `GET /invoices/{id}/line-items` to reconstruct a cart from, navigating away from
  Catalog would have discarded whatever was added regardless.
- **The fix**: consolidated `CatalogViewModel`/`CartViewModel`/`PaymentViewModel` into one
  `SellViewModel` scoped to a new nested "sell" nav sub-graph wrapping Catalog/Cart/Payment
  (`hiltViewModel(navController.getBackStackEntry("sell"))` — the standard Compose Navigation pattern
  for a ViewModel shared across a set of screens). Tapping a product now calls `addToCart(productId)`,
  which opens the draft invoice on the first tap and appends a line item on every tap after; Catalog
  gained a "View Cart — N items · $X.XX" bottom bar instead of auto-navigating away per tap. Completing
  payment re-navigates to the sell graph's own route with `popUpTo(...) { inclusive = true }`, which
  discards the graph's back stack entry (and with it the `SellViewModel` instance) — a clean cart reset
  for the next sale, for free.
- Still generic, non-exact-match UI (a plain product grid, a plain line-item list, plain Cash/Card/
  Split buttons) — the design-bundle-exact Register screen and modifier sheet are the next slice.

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

**What the self-service license-seat auth rework shipped** (this session, on top of everything above
— see PR #110 backend+portal, branch `claude/session-a61ycb` for the Android slice): user feedback
after exercising the real login flow on an emulator — hitting the Device Setup screen was an
unexpected, undocumented prerequisite ("I wasn't aware of the new page") — led to reworking the whole
model instead of just polishing that screen. The admin-pre-registration flow (portal admin registers
a device via `POST /pos-devices`, someone types the resulting `device_token` into Device Setup before
Login even works) is replaced with self-service: log in with credentials only, pick a site from your
own grants, and the app claims (or re-pairs) a license seat automatically.
- **Backend**: `licenses.max_devices` (migration `0051`) is the new seat-capacity concept — licenses
  had none before, just a 1-device-1-site pairing with no cap on how many devices could attach.
  `pos_auth_service.login()`/`select_site()` no longer resolve the site from a device's own pairing at
  all — site resolution is now purely `UserAccessGrant`-driven (one grant auto-resolves, zero is a
  403, two+ returns `available_sites` **unconditionally**, superseding `is_pos_multi_site_enabled`'s
  former gating role — the flag/column/portal toggle still exist, just unused by this decision now).
  `_finalize_login()`'s new `_resolve_or_claim_device()` reuses an already-paired device on the
  resolved site as-is, re-pairs it elsewhere (`DEVICE_REPAIRED`), or claims a brand-new one
  (`DEVICE_REGISTERED`) — the latter two gated by the license's remaining seats, `403` if none are
  free. New `GET /pos-devices/management` + `POST /pos-devices/{id}/release` let a management-portal
  user (permission- and scope-gated by the existing `"devices"` page key) or a portal admin (any
  device) free a seat; the superadmin-only manual-registration routes from the original slice are
  unchanged as an escape hatch, not removed.
- **Portal**: `LicensesPage` gained a seat-capacity field + a click-to-edit "N of M seats" column; new
  management-portal `DevicesPage.tsx` (nav entry "Devices") lists the caller's scoped devices with a
  Release action.
- **Android**: `DeviceSetupScreen.kt`/`DeviceViewModel.kt` and `Screen.DeviceSetup` are deleted
  outright — `StartDestination` is now just `Login` vs `RegisterGate`, nothing to resolve ahead of
  Login. `TokenStore.deviceToken` stays structurally the same (still "this terminal's own persisted
  token") but is now populated automatically from a login response instead of manual entry —
  `AuthRepository.pairDevice()`/`hasPairedDevice()`/`requireDeviceToken()` are gone, replaced by an
  internal `saveDeviceToken()` called after every successful login/site-select. `LoginRequest`/
  `SiteTokenRequest` send `device_name` (sourced from `android.os.Build.MODEL` — no rename screen
  exists yet, flagged as an easy follow-up if wanted) and a nullable `device_token` (whatever's
  locally stored, `null` on first-ever login); `PosLoginResponseDto` gains the claimed/re-paired
  `device_token` to persist. `AuthViewModel.loginErrorMessage()` gained a 403 sub-case (checks the
  error body for "seat") distinguishing "no available license seats" from a plain no-grant 403 — the
  first HTTP-body-content-based error mapping in this file, everything else there is status-code-only.
- **Not verified against a real build** — same standing caveat as the original auth slice above (this
  sandbox can't reach Google's Maven repo); relies on the GitHub Actions Android CI job added this
  session plus a manual grep sweep for stale call sites (`DeviceSetup`, `pairDevice`,
  `hasPairedDevice`, `requireDeviceToken`, `DevicePairState`, `DeviceViewModel` — all confirmed zero
  remaining references).

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
- ✅ Add `is_pos_multi_site_enabled` to `User`, and expose it as an editable toggle on the management
  portal's Users edit page (labelled "POS - Site Assignment").
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
- ✅ Register-session **portal report** — `GET /register-session-reports` (new
  `register_session_report_service.py` / `routes/register_session_reports.py`, mirroring the
  `invoice_service.py`/`invoice_report_service.py` transactional-vs-reporting split): filtered
  (site/device/status/date-range), paginated list joined to `pos_devices`/`sites` for
  `device_name`/`site_name`, with opening/closing cash, computed `cash_takings_cents`
  (`expected_cash_cents - opening_cash_cents`), variance, and who opened/closed each session. Uses
  the same `CatalogAccess`/`effective_brand_id`/site-scope-guard pattern `invoice_reports.py`
  established, so POS terminals, site-scope management users, brand/group-scope, and portal admin
  callers are all scoped correctly.
- ✅ Portal report page — `RegisterSessionsPage.tsx`, reachable from the management nav and as a new
  tab on the SuperAdmin's Brand detail page (same placement as `InvoicesPage`). Session volume is
  small per the service docstring (one row per device per shift), so unlike Invoices this page
  `fetchAll`s the brand/site's full list and filters client-side (status, terminal, date range) — no
  server-side pagination needed. The terminal filter's options are derived from the loaded rows
  rather than a separate device-list fetch, since `GET /pos-devices` is portal-admin-only and has no
  brand/site scoping a management user could use.

**Android**
- ✅ Project wiring: Retrofit client, Hilt DI modules, Room DB, Compose nav graph (existing Stage 25
  scaffolding, filled in for real — see "What the Android auth slice actually shipped" above).
- ~~**Device Setup** screen~~ — built in this slice (not in the original list — see above for why it
  was a hard prerequisite at the time), then **removed** by the self-service auth rework noted above:
  a terminal no longer needs one-time `device_token` entry, it claims a seat automatically on login.
- ✅ **Login** screen (email + password, ZedRead wordmark). Calls `POST /auth/pos/login` with
  `{email, password, device_token}`. Still needs the Public Sans 700 / Register-surface type
  treatment pass — functionally wired but not yet styled to the design bundle.
- ✅ **PIN entry** — folded into **SwitchUserScreen** (email + PIN, "current user" context line)
  rather than shipped as a second, functionally-identical screen — see above.
- ✅ **Site selector** screen — shown only when login returns `available_sites`; re-pairs the device
  when a non-paired site is chosen (backend-side, per `_finalize_login`). Calls
  `POST /auth/pos/site-token` with the chosen `site_id`. Still needs the inline re-pair notice copy.
- 🔲 **Register / order-entry screen** — exact match to `ZedRead Register.dc.html`: header, category
  rail, product grid (text-only + with-image tiles), order pane (ticket header, order-type segmented
  control, line list with qty stepper, totals footer, Hold/Pay). `CatalogScreen` scaffolding exists
  but is a generic grid, not the exact-match design.
- 🔲 **Modifier customise sheet** — exact match (slide-over, group blocks, qty stepper, live total).
- 🔲 **Payment flow** — exact match for Card/Cash tabs and the Choosing/Done states, **plus one
  flagged addition**: a third **Voucher** tab (reference-code input, same visual language as Card)
  and a **Split** toggle on Cash/Card (partial amount + "Add another payment" keeps the modal open
  with a running "remaining due") — since the mockup predates the voucher/split backend capability.
- 🔲 Basic online invoice creation (no offline queue yet — that's Phase 2).
- ✅ `GET /register-sessions/current` gate on launch/resume, routing to cash-in if null before
  allowing a sale (`RegisterGateScreen`) — `POST /invoices` returns 400 otherwise.
- ✅ **Start-of-day cash-in**: bulk-value entry (denomination-breakdown variant is a Phase 2
  setting); blocks Register access until a session is open. Calls `POST /register-sessions/open`
  (`CashInScreen`).
- 🔲 **End-of-day cash-up**: bulk-value entry compared against expected takings, variance shown (the
  hide-variance option is a Phase 2 setting); confirm-close. A "Cash Up" entry point in the
  account/nav menu. Calls `POST /register-sessions/{id}/close`.

**Backend API reference for Phase 1 Android work** (current contract — see the self-service
auth-rework note above for how this superseded the original device-paired shape):
- `POST /auth/pos/login` `{email, password, device_name, device_token?}` → token (incl. the claimed/
  re-paired `device_token` to persist), or `{available_sites: [...]}`. `device_token` is the
  terminal's own previously-claimed token, `null`/omitted on first-ever login.
- `POST /auth/pos/site-token` `{email, password, device_name, device_token?, site_id}` → token.
- `GET /register-sessions/current` → open session for this device, or `null`.
- `POST /register-sessions/open` `{opened_at, opening_cash_cents}` → session.
- `POST /register-sessions/{session_id}/close` `{closed_at, closing_cash_cents}` → session with
  computed `expected_cash_cents`/`variance_cents`.
- `POST /invoices` — now requires an open register session for the device (400 otherwise); response
  includes `register_session_id`.
- `GET /register-session-reports` — portal/management report: filtered, paginated register-session
  list (see above). Not an Android-consumed endpoint — listed here since it completes the till
  round-trip Phase 1 needs before the report *page* can be built.

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
