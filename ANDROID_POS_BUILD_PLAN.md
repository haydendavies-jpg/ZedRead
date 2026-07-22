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
| 1 | Android — Register-session gate + start-of-day cash-in / end-of-day cash-up screens | ✅ Done |
| 1 | Android — functional (non-exact-match) sell loop: browse → cart → pay | ✅ Done — see below |
| 1 | Android — Register (order-entry) screen, exact match to design bundle | ✅ Done — see below |
| 1 | Backend — invoice line-item quantity update / remove (qty stepper support) | ✅ Done |
| 1 | Android — Modifier customise sheet, exact match | ✅ Done — see below |
| 1 | Android — Payment flow, exact match + Voucher tab/Split toggle | ✅ Done — see below |
| 1 | Android — user-testing feedback round (cash-up logout, keyboard/IME, immersive system bars, PIN-only switch-user) | ✅ Done — see below |
| 2 | Backend — settings framework, idempotency, checksum verification | ✅ Done — see below |
| 2 | Portal — Settings management page | ✅ Done |
| 1 | Backend/Android — hardware-anchored device recognition (`pos_devices.hardware_id`, survives reinstall) | ✅ Done — see below |
| — | Portal — brand-scoped License & Billing page (seat editing for Admin/Master User, not just SuperAdmin) | ✅ Done — see below |
| 2 | Android — Settings screen + denomination-grid cash-in/cash-up variant | ✅ Done — see below |
| 2 | Android — offline write-queue, sync indicator, invoice search | 🔲 Not started |
| 3 | Menu Studio → POS integration depth (recurring scheduling, menu selector) | 🔲 Not started |
| 4 | Table maps & floor service | 🔲 Not started |

**Next up:** Phase 1 is functionally complete on both backend and Android, including a round of fixes
from real on-device testing. What's left before calling Phase 1 fully done is verification: a real
Gradle build + emulator run (still blocked in this sandbox, see below) and manual exercise of the till
round-trip end to end. One item from this round's feedback is still open pending user input — see
"colour branding" below. Phase 2's backend foundations (settings framework, idempotency, checksum
verification — items 1–3 of that phase's build order) are done. Item 4 (Android Settings screen +
denomination-grid cash-in/cash-up variant) is also done, proving the settings pattern end to end on
Android — see "What the Phase 2 Android settings slice shipped" below. Next: Phase 2 items 5–7
(offline write-queue, sync indicator, invoice search) — deliberately not started this session per
this plan's own "stop after #4 rather than leaving the offline queue half-built" guidance; the
write-queue needs a new WorkManager dependency and a Room outbox schema that deserve their own
focused session rather than a partial cut. See `STAGE_STATUS.md`'s "Android POS Phase 2" entries for
full detail.

**What the Phase 2 Android settings slice shipped** (this session): `GET /pos/settings` consumed
for the first time — a new `SettingDto`/`PosApiService.getSettings()` (mirrors `SettingOut` exactly;
the polymorphic `default_value`/`brand_value`/`site_value`/`effective_value` fields are typed `Any?`,
resolved by Moshi's built-in Any/Object adapter rather than a registered custom one — the same
mechanism that already backs `Map<String, Any>` parsing elsewhere in the Moshi ecosystem) and a new
`SettingsRepository` (no local Room cache — unlike the product catalog, settings are small and read
fresh each time a screen needs them). A new read-only **Settings screen**
(`SettingsScreen.kt`/`SettingsViewModel.kt`) lists every setting resolved for the terminal's site,
search-filterable client-side by key/label/category; a gear icon on the Register header (next to the
existing Cash-up/Switch-operator icons) opens it — editing overrides stays a portal-only capability,
matching the backend's own read-only `GET /pos/settings` contract. `CashInScreen`/`CashUpScreen` each
gained the **denomination-grid** variant (`CashDenominationGrid.kt`'s `DenominationGrid` composable —
standard AUD note/coin rows, blank by default so an untouched row can't be mistaken for a
counted-and-confirmed zero, reporting a running total in cents) toggled by the `cash_in_mode` setting,
and `CashUpScreen`'s Expected/Counted/Variance summary collapses to Counted-only when
`hide_variance_on_close` is set — both read via a new `RegisterSessionViewModel.loadCashSettings()`
backed by `SettingsRepository.getCashSettings()`, which defaults to bulk-entry/variance-shown (the
catalog's own defaults) if the settings fetch fails, so a settings outage never blocks a till
open/close. **Not verified against a real build** — same standing constraint as every prior Android
slice (this sandbox can't reach Google's Maven repo); checked via a manual brace/paren balance pass
on every new/changed file, a cross-reference of every new type/import against its definition, and a
repo-wide grep for stale call sites (`OrderEntryScreen(` for the new `onSettings` parameter, `Screen.
Settings`, `getSettings(`) — all confirmed consistent. Needs a real compile + emulator run before
merging with confidence.

**What the license-editing + device-tracking slice shipped** (this session): two user requests. (1)
Brand-scoped Admin/Master User can now edit a license's seat capacity via a new `license_billing`-
gated `/licenses/management` route family and a new portal "License & Billing" page — previously the
`license_billing` page permission existed in the role model but nothing was wired to it, so only
SuperAdmin could touch `/licenses` at all. (2) Device tracking across app reinstalls: `device_token`
alone can't survive a reinstall (it lives in the app's own storage, wiped with it), and MAC address
was explicitly ruled out (Android randomizes/blocks it for privacy). `pos_devices.hardware_id`
(migration `0054`) stores Android's `Settings.Secure.ANDROID_ID`, read fresh from the OS on every
login and sent alongside `device_token`; `pos_auth_service` now falls back to a hardware_id lookup
when no token is presented, re-linking a returning physical device instead of silently claiming a
new seat. See `STAGE_STATUS.md` "License editing for Admin/Master User + hardware-anchored device
tracking" for the full deliverable list — the 109 tests directly covering this slice, and the full
suite (904/904, up from 889), pass against a real local Postgres 16; portal `npm run build` clean;
the Android-side change (`AuthRepository` reading `ANDROID_ID`) is source-only, same "no reachable
Gradle build in this sandbox" caveat as everything else here.

**What the Phase 2 backend/portal slice shipped** (this session): the first three items of Phase 2's
build order, fully tested against a real Postgres instance — see `STAGE_STATUS.md` "Android POS
Phase 2 — Settings, Idempotency & Checksum Verification" for the complete deliverable list. In brief:
a `setting_values` table (site-scoped, brand-level fallback, migration `0052`) backed by a code-defined
catalog (`app/constants/settings.py`, mirroring `app/constants/pages.py`'s pattern) seeded with
`cash_in_mode` and `hide_variance_on_close`, exposed via `GET/PUT/DELETE /settings` (management,
gated by the pre-existing `site_settings` page permission) and a read-only `GET /pos/settings`; a
`client_ref` idempotency key (migration `0053`) deduping `POST /invoices`, `POST .../pay`, and
`POST /register-sessions/open`/`.../close`; and a SHA-256 checksum (`app/utils/checksum.py`) verified
server-side and echoed back, computed for an invoice at the **pay** call (once its line items/totals/
payments are actually known — an invoice is built up incrementally, unlike a register session's
single-call open/close) and for a register session at open and again at close. Portal gained
`SettingsPage.tsx`. 33 new backend tests, full suite 889/889 passing (up from 856); `npm run build`
verified clean.

**What the user-testing feedback round shipped** (this session, on top of the modifier sheet + payment
flow slice below): six issues reported from exercising the real app, addressed —
- **Cash-up no longer forces logout.** `CashUpScreen`'s post-close screen previously offered only a
  "Log Out" button as its sole next action (`RegisterSessionViewModel.logout()`/`loggedOut`, both now
  removed — dead once their only caller was gone). It now just says "Done" and returns to
  `RegisterGate` (which prompts cash-in for the next shift since no session is open) — the operator
  stays logged in on the device. Logging out is a separate, explicit action that belongs in a future
  Settings screen (Phase 2, not built yet), not something cash-up should force.
- **Keyboard no longer covers input fields.** `windowSoftInputMode="adjustResize"` alone doesn't resize
  an edge-to-edge window (`enableEdgeToEdge()`, already in use) the way it did pre-edge-to-edge — none
  of the six screens with text fields (Login, PinSet, SwitchUser, CashIn, CashUp, the payment modal's
  split-amount/voucher-reference fields) applied `Modifier.imePadding()`. Added it to each; the one
  Scaffold-based screen (SwitchUser) also got `contentWindowInsets = WindowInsets(0.dp)` to opt out of
  Scaffold's own (version-dependent) inset handling first, avoiding a double-padding risk.
- **System status/nav bars hidden.** `MainActivity` now hides system bars immersively on create and
  re-hides on every `onWindowFocusChanged(true)` (a transient reveal via edge-swipe, or returning from
  recents/another app, both clear the hidden state) — `WindowInsetsControllerCompat.hide(systemBars())`
  with `BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE`. A POS terminal has no business showing the clock,
  notifications, or a back/home/recents bar during a sale.
- **Switch-operator asks for a PIN only, not email.** Real POS terminals overwhelmingly support this
  (Square, Toast, Lightspeed) — staff shouldn't re-type an email every time they take over the
  terminal. Backend: `PINVerifyRequest.email` is now optional; supplying it keeps the original
  single-account check (still used by the inline manager-authorisation prompt, which needs a
  *specific* manager, not "any staff"), omitting it (`_pin_candidates_by_site()`, new) checks the PIN
  against every active user holding a site-scoped grant at `site_id` instead — the same "fail closed on
  an unresolved collision" policy the email-scoped path (`_pin_candidates_by_email()`, extracted
  unchanged from the original function) already applied to its own multi-identity case, now also
  covering two different staff independently picking the same PIN. `PINVerifyResponse` gained a
  nullable `email` field so a PIN-only switch can still persist which account is now active locally
  (`users.email` itself is nullable — auto-created Master Users have none). 4 new backend tests
  (PIN-only happy path, wrong PIN, audit log, same-PIN collision → 403); full suite 856/856 passing.
  Android: `SwitchUserScreen` dropped its email field entirely; `AuthRepository.verifyPin()` split into
  `verifyPinAndSwitch(pin)` (adopts the result as the active session — switch-user) and
  `verifyPinOnly(email, pin)` (no session change — manager auth) — the shared implementation
  previously had `authorizeManager()` silently *also* adopt the manager's session on every call despite
  its own docstring's "does not change the active cashier session" claim, a latent bug now fixed as
  part of the same split (the inline manager-auth prompt isn't wired to any screen yet, so this was
  unreachable in practice, but would have bitten the moment it was).
- **Modifier comboing confirmed out of scope, not a bug.** Nested/linked modifier groups
  (`modifier_option_group_links`) are a Menu Studio (portal catalog admin) feature only — the Register
  screen's modifier sheet spec (`ZedRead Register.dc.html`) has no comboing UI, and no phase in this
  plan schedules it for the POS runtime. Confirmed via a grep sweep of this file before disregarding,
  per the report's own "if that's a later phase, disregard" framing.
- **Colour branding — not actionable without more input.** Reported: "red buttons backgrounds have
  been replaced with new colour branding." `Theme.kt`'s colours were checked against
  `design_handoff_zedread/README.md`'s own documented palette and match it exactly (including the
  `#A82040` accent red used for primary buttons via Material3's `primary` → `accent` mapping, so
  standard `Button()`s already render correctly under the *current* documented design) — there's no
  implementation drift to fix here. Nothing in the repository indicates what the new colour actually
  is (no updated design file, logo, or style guide committed). Flagged rather than guessed; needs an
  actual hex value (or a reference to sample one from) before this can be addressed.

**What the modifier sheet + payment flow slice shipped** (this session): the two remaining Phase 1
Android pieces, plus three backend fixes surfaced while wiring them up.
- **Backend — new POS-reachable read endpoint**: `GET /products/{id}/modifiers/detailed`
  (`modifier_service.list_product_modifiers_detailed()` + `routes/modifiers.py`) returns a product's
  *attached* modifier groups fully nested with their active options (name, `price_delta_cents`) — the
  existing `GET /products/{id}/modifiers` only returns option *counts* (it powers the portal's
  attach/reorder picker, not a selection UI), and `GET /modifier-groups/detailed` returns every group
  in the *brand*, unfiltered, plus comboing links and a `used_by_count` the POS doesn't need. Confirmed
  `resolve_catalog_access` already accepts POS tokens (tried in order: portal → management → POS), so
  no new auth path was needed, just the new query shape.
- **Backend — `pay_invoice()` split-payment bug, found and fixed**: the route previously set
  `invoice.status = PAID` unconditionally on the *first* payment call regardless of amount — a $5
  payment against a $30 invoice silently marked the whole invoice paid. The `Payment` model's own
  docstring already documented the intended contract ("PAID once the sum of payments >= total_cents");
  `pay_invoice()` just didn't implement it. Fixed to sum all payments (via `func.sum()`, cast to `int`
  since asyncpg returns a `Decimal` for a `SUM()` over `BigInteger` — that Decimal isn't JSON-serializable
  and broke the audit log's `after_state` until cast) and only flip to `PAID` once covered; a
  not-yet-covered leg now writes a new `INVOICE_PAYMENT_RECORDED` audit action instead of `INVOICE_PAID`
  so the audit trail doesn't claim "paid" prematurely. This was a real, pre-existing bug the Split
  toggle's own correctness depends on, not something introduced by this slice.
- **Backend — `add_line_modifier()` missing audit log, found and fixed**: the route had no
  `log_action()` call at all — a violation of the project's absolute rule 7, invisible until this
  session made the endpoint load-bearing for the first time (nothing called it before). Added
  `INVOICE_LINE_ITEM_MODIFIER_ADDED` and the missing call.
- **Backend — new `GET /invoices/{id}/line-items/{id}`**: `POST .../modifiers` returns only the
  created `LineModifierResponse` row, not the parent line — and a line's own `subtotal_cents`/
  `line_total_cents` never reflect its modifiers regardless (only the *invoice's* aggregate total does,
  via `_recompute_invoice_totals()`'s separate `InvoiceLineModifier` query — a modifier is a flat
  per-line addition, not scaled by quantity, an existing limitation of `invoice_line_modifiers`'
  schema, not something this slice changed or could cleanly fix without a bigger invoice-engine rework;
  flagged in `STAGE_STATUS.md`'s Known Gaps). The new route (`LineItemDetailResponse` = `LineItemResponse`
  + `modifiers: list[LineModifierResponse]`) lets the Android client fetch a line's accumulated
  modifiers after attaching them, to display "· modifier" sub-lines and a modifier-inclusive line total.
- **Backend tests**: 12 new integration tests (product-modifiers-detailed happy path/unattached/
  inactive-options/404/403; line-modifier audit log; line-item-detail happy path/404; partial-payment
  leaves invoice open/second-leg completes it/writes the right audit action; full-payment still writes
  `INVOICE_PAID`) — full suite 852/852 passing (up from 840), verified against a real local Postgres 16
  instance with migrations applied through `0051`.
- **`SellViewModel`**: `addToCart()` is now a dispatcher — a product with a non-blank `modifierNames`
  (the same field backing the grid's "+" badge) opens the modifier sheet instead of adding directly.
  New modifier-sheet state machine (`ModifierSheetState`: `Closed`/`Loading`/`Ready`/`Error`,
  `ModifierGroupSelection` tracking per-group selected option indices) mirrors the mockup's own
  `mod`/`toggleChoice`/`modAddToOrder` logic exactly: single-select groups default to their first
  option and always keep exactly one selected; multi-select groups toggle freely; on confirm, a
  single-select choice is always attached as a line modifier (even a free one, so it still shows on
  the receipt) while a multi-select choice is only attached when priced — the mockup's
  `c.price>0 || g.type==='single'` filter, reproduced verbatim. `subtotalCents`/`taxCents`/`totalCents`
  are now computed including each line's modifier total (mirroring `_recompute_invoice_totals()`
  exactly) instead of ignoring modifiers entirely, which they previously did since nothing attached
  modifiers before this slice.
- **New payment state machine**: replaces the old `PaymentFlowState`/`pay()` pair with a single
  `PaymentUiState` (stage/method/tendered/splitMode/splitAmountCents/voucherReference/paidCents)
  mirroring the mockup's own `pay: {stage, method, tendered}` shape, extended with the split/voucher
  fields the mockup predates. `submitPayment()` reads the real `InvoiceDto.status` from
  `POST .../pay` to decide Done vs. "leg recorded, remaining due updated" — now meaningful now that
  the backend bug above is fixed.
- **Both the modifier sheet and payment modal are overlays on the Register screen itself, not separate
  nav destinations** — matching the design bundle's own architecture (`ZedRead Register.dc.html`'s
  `mod`/`pay` state live alongside `order[]` on one Component, not routed). This let the earlier
  "sell" nav sub-graph (`Screen.SellGraph`, built to share one `SellViewModel` across
  `OrderEntryScreen`/`PaymentScreen` as separate destinations) be deleted entirely: `Screen.OrderEntry`
  is now a single flat destination, `SellViewModel` scopes to it via the default `hiltViewModel()`, and
  "New order" resets cart/payment state in place (`completePaymentAndStartNewOrder()`) instead of the
  previous navigate-and-`popUpTo` trick to discard the ViewModel instance. `RegisterGateScreen`/
  `CashInScreen` now navigate straight to `Screen.OrderEntry.route`.
- New `ModifierSheet.kt` (`ModifierSheetOverlay` + group/choice-row/footer composables) and a rewritten
  `PaymentScreen.kt` (`PaymentModal` + Choosing/Done content, Card/Cash/Voucher tabs, split-amount
  entry) — both exact-match to the design bundle's spacing/colors/interaction per
  `design_handoff_zedread/README.md` and cross-checked against `ZedRead Register.dc.html`'s actual
  markup/state logic for anything the README left ambiguous (rule-chip text, tender-preset computation,
  mark glyphs, selection defaults).
- **Not verified against a real build** — same standing constraint as every prior Android slice: this
  sandbox cannot reach Google's Maven repo (`gradle :app:compileDebugKotlin` fails at AGP plugin
  resolution, confirmed again this session). Relied on a careful manual read-through of every changed/
  new file (brace/paren balance checked, every type and import cross-referenced against its
  definition) plus a repo-wide grep for stale symbols (`PaymentFlowState`, `Screen.Payment`,
  `Screen.SellGraph`, `sellViewModel(`, `onProceedToPayment` — all confirmed zero remaining
  references) instead of a build. Needs a real compile + emulator run before merging with confidence.

**What the exact-match Register screen slice shipped** (this session, branch
`claude/next-stage-hl4xwg`): rebuilt the order-entry screen from
`design_handoff_zedread/README.md`'s "Register (order entry)" spec — header, category rail, product
grid, order pane — replacing the earlier generic `CatalogScreen`/`CartScreen` pair entirely (the
design has no separate cart screen; the order pane sits beside the grid on one screen at all times).
- **Backend**: the qty stepper needed primitives the invoice engine didn't have — `PATCH
  /invoices/{id}/line-items/{lineItemId}` (rescales a line's quantity from its already-snapshotted
  per-unit price/tax, never re-fetches the product) and `DELETE /invoices/{id}/line-items/{lineItemId}`
  (removes a line, recomputes invoice totals), both in `invoice_service.py`/`routes/invoices.py`, each
  gated to draft/open invoices (409 otherwise) and audited (`INVOICE_LINE_ITEM_QUANTITY_UPDATED`/
  `INVOICE_LINE_ITEM_REMOVED`). `invoice_tax_breakdowns` has no FK back to the line item that produced
  each row, so a quantity change or removal can't surgically patch one row — both new functions instead
  call a new `_rebuild_tax_breakdown()` that deletes and reinserts the invoice's breakdown rows from its
  current line items, keeping the same one-row-per-taxable-line shape `add_line_item()` already
  produces. 8 new integration tests (quantity rescale + tax recompute, 404, 409-on-paid, audit rows,
  for both routes) — full backend suite still 840/840 passing (up from 832, this session's 8 additions),
  verified against a real local Postgres 16 instance with migrations applied through `0051`.
- **Design tokens**: `Theme.kt` gained the full `README.md` "Shared design system" color set (light +
  dark, both — the app now follows system dark mode automatically) as a `ZedReadColors` data class via
  `LocalZedReadColors`, since several tokens (`surface2`, `border`, `accent-soft`, `green`) have no
  matching Material3 colorScheme slot. Also added `parseHexColor()`/`contrastTextColor()` (the design's
  "luminance test" rule for tile text color against an arbitrary category fill). **Font swap deferred**
  — Public Sans / IBM Plex Sans / IBM Plex Mono would need the downloadable-fonts API (new Gradle
  dependency + certificate config) and are left as system-default sans-serif for now, flagged as a
  follow-up rather than risked unverified in this sandbox (no reachable Google Maven here — see below).
- **`GET /products`/`GET /categories` already returned `category_color`/`modifier_names`/
  `default_color`** (Stage 20/the Menu Studio redesign) but the Android DTOs and Room cache never
  captured them — added to `ProductDto`/`CategoryDto`, `ProductEntity`/`CategoryEntity` (Room DB version
  bumped to 2 — `fallbackToDestructiveMigration()` was already wired, so no migration needed, cache-only
  data), and `CatalogRepository.refresh()`'s mapping. These power the tile/rail fill colors and the
  "has modifiers" "+" badge.
- **`OrderEntryScreen.kt`** (new package `ui/screens/orderentry/`, replacing `ui/screens/catalog/` +
  `ui/screens/cart/`): header (title + selected-category subtitle — the mockup's venue-name subtitle
  was placeholder sample text, replaced with something actually dynamic rather than hardcoded fake
  copy), 200dp category rail (active row filled with the category's `default_color`, contrast text),
  product grid (tile filled with `category_color`, text-only vs with-image variant by `photoUrl`
  presence via Coil `AsyncImage`, "+" badge when `modifierNames` is non-blank), and the order pane
  (ticket-number chip, order-type segmented control, line list with a working qty stepper + tap-to-
  select highlight, totals footer, Hold + Pay). `SellViewModel` gained `setLineQuantity()`/`removeLine()`
  (wired to the new backend routes), `clearOrder()` (the ✕/Hold action), and local-only `ticketNumber`/
  `orderType`/`selectedLineItemId` state.
  - **Two flagged gaps, both pre-existing limits the exact-match layout surfaces rather than causes**:
    the order-type segmented control (Dine-in/Takeaway) and ticket number are **visual only** — no
    `invoice_type`/ticket-number column exists on `Invoice` to persist them, and the ticket number
    resets every app relaunch (in-memory counter, not persisted). **Hold** clears the order pane but
    does not void/delete the underlying invoice — it's simply left open/uncollected server-side, since
    there's no "recall a held order" list yet to bring it back to.
  - Switch-operator and cash-up controls (previously on `CatalogScreen`'s `TopAppBar`) moved to icon
    buttons on the new header — the design's real home for them is the persistent top nav bar
    (`README-tables-floormap.md`, Phase 4 scope), so this is a functional stand-in, not the final
    placement.
- **Not verified against a real build** — same standing constraint as every prior Android slice: this
  sandbox cannot reach Google's Maven repo (`gradle :app:compileDebugKotlin` still fails at AGP plugin
  resolution, confirmed again this session), so relies on the repo's `Android build` CI job plus a
  manual grep sweep for stale symbols (`CatalogScreen`, `CartScreen`, `Screen.Catalog`, `Screen.Cart` —
  all confirmed zero remaining references) before merging with confidence.

**What the end-of-day cash-up slice shipped** (this session, branch `claude/next-stage-hl4xwg`):
a new `CashUpScreen.kt` mirrors `CashInScreen.kt`'s bulk-value-entry pattern — loads the terminal's
open session (`GET /register-sessions/current`), takes a closing-cash amount, calls
`POST /register-sessions/{id}/close`, then shows the computed Expected/Counted/Variance summary
before logging the operator out (`AuthRepository.logout()` — the device stays paired for the next
shift, matching the "device stays pinned" architecture decision). `RegisterSessionViewModel` gained
the matching `CashUpState` state machine (`Loading`/`Ready`/`Submitting`/`Closed`/`Error`) and a
`logout()`/`loggedOut` pair alongside its existing cash-in state. Entry point: since there's no
account/nav menu yet (out of scope until the exact-match Register header ships), a "Cash up" icon
button was added to `CatalogScreen`'s existing `TopAppBar` next to the switch-operator icon —
functional placement, not the design bundle's styling. Wired into `PosNavHost` as a new `cash_up`
route that clears the whole back stack back to Login on completion, so Back can't return to a stale
sale after a shift ends.

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
- ✅ **Register / order-entry screen** — exact match to `ZedRead Register.dc.html`: header, category
  rail, product grid (text-only + with-image tiles), order pane (ticket header, order-type segmented
  control, line list with qty stepper, totals footer, Hold/Pay).
- ✅ **Modifier customise sheet** — exact match (slide-over, group blocks, qty stepper, live total).
- ✅ **Payment flow** — exact match for Card/Cash tabs and the Choosing/Done states, **plus one
  flagged addition**: a third **Voucher** tab (reference-code input, same visual language as Card)
  and a **Split** toggle on Cash/Card (partial amount + "Add another payment" keeps the modal open
  with a running "remaining due") — since the mockup predates the voucher/split backend capability.
- 🔲 Basic online invoice creation (no offline queue yet — that's Phase 2).
- ✅ `GET /register-sessions/current` gate on launch/resume, routing to cash-in if null before
  allowing a sale (`RegisterGateScreen`) — `POST /invoices` returns 400 otherwise.
- ✅ **Start-of-day cash-in**: bulk-value entry (denomination-breakdown variant is a Phase 2
  setting); blocks Register access until a session is open. Calls `POST /register-sessions/open`
  (`CashInScreen`).
- ✅ **End-of-day cash-up**: bulk-value entry compared against expected takings, variance shown (the
  hide-variance option is a Phase 2 setting); confirm-close, then logs the operator out. A "Cash up"
  icon button on `CatalogScreen`'s top bar is the entry point for now (no account/nav menu exists
  yet — that's design-bundle-dependent). Calls `POST /register-sessions/{id}/close` (`CashUpScreen`).

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
- `PATCH /invoices/{id}/line-items/{lineItemId}` `{quantity}` → updated line — the Register screen's
  qty stepper.
- `DELETE /invoices/{id}/line-items/{lineItemId}` → 204 — removes a line from the order.
- `GET /invoices/{id}/line-items/{lineItemId}` → the line plus its attached modifiers — refreshes
  display state (modifier sub-lines, modifier-inclusive total) after the modifier sheet attaches one
  or more modifiers, since `POST .../modifiers` itself only returns the created modifier row.
- `GET /products/{id}/modifiers/detailed` → the product's attached modifier groups, each fully nested
  with its active options (`price_delta_cents` included) — powers the modifier customise sheet.
- `POST /invoices/{id}/line-items/{lineItemId}/modifiers` `{modifier_option_id}` → attaches one
  modifier selection; the sheet calls this once per qualifying selection on confirm.
- `POST /invoices/{id}/pay` `{method: cash|card|voucher, amount_cents, reference?}` → invoice with
  `status` only `"paid"` once the sum of all payments recorded against it covers `total_cents` — a
  smaller amount records a split-payment leg and leaves the invoice `"open"`. `reference` carries a
  voucher's redemption code.
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
