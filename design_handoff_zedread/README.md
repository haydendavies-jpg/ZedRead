# Handoff: ZedRead POS — Full Product

This is the **master handoff** for the ZedRead hospitality point-of-sale product. It covers both software surfaces and links out to two detailed area docs. Read this file first.

## What ZedRead is
ZedRead is a café/restaurant POS with two distinct surfaces that share one design language:

1. **ZedRead Register** — the front-of-house / staff-facing app run on the register. Screens: **Register** (ring up an order), **Tables** (live floor map), **Online** (delivery/pickup order queue), plus a **modifier customise sheet** and a **payment flow**.
2. **ZedRead Menu Studio** — the back-office / manager admin. Manages the catalog (Products, Modifiers, Categories), reporting groups, POS button layouts, and published Menus with scheduling.

They are separate apps in the same product family, not two views of one app.

## About the design files
Every `*.dc.html` file in this bundle is a **design reference built in HTML** — an interactive prototype showing intended look, structure, and behavior. They are **NOT production code to copy directly**. The task is to **recreate these designs in the target codebase's environment** (React, Vue, SwiftUI, native, etc.) using its established component patterns, state management, and data layer. If no frontend exists yet, pick the most appropriate framework and implement there.

To view any file, open it directly in a browser — each is self-contained (needs the sibling `support.js`, which is the prototype runtime, NOT something to ship).

All product/table/order data is **placeholder sample data** for the mockups — wire up to real data in implementation.

## Fidelity
**High-fidelity.** Colors, typography, spacing, and interactions are intended as final or near-final. Treat the hex values, font sizes, and spacing in these docs as authoritative unless the target design system dictates otherwise — flag conflicts rather than silently overriding.

---

## Documentation index
- **`README.md`** (this file) — product overview, shared design system, and full docs for the **Register**, **Online**, **Modifier sheet**, and **Payment** screens (not covered elsewhere).
- **`README-tables-floormap.md`** — deep dive on the **Tables / Floor Map** screen and the persistent **top navigation bar** (part of the Register app).
- **`README-menu-studio.md`** — deep dive on the entire **Menu Studio** admin (Products / Modifiers / Categories tabs, POS Layout editor, Menus screen) and the modifier-comboing pattern.

## Files in this bundle
- `ZedRead Register.dc.html` — the whole front-of-house app (Register, Tables, Online, modifier sheet, payment). Single Design Component.
- `ZedRead Menu Studio.dc.html` — the whole admin app.
- `Modifier Comboing Options.dc.html` — exploration of the modifier "comboing" (linked option groups) interaction; the chosen option (inline nested cascade) is integrated into Menu Studio. Reference for intent only.
- `support.js` — prototype runtime for the `.dc.html` files. Not for production.
- `uploads/images.jpg` — the one raster asset used (a product-tile photo on the "Latte" product in Register). Everything else is CSS/SVG/Unicode.

---

## Shared design system (applies to BOTH apps)

### Colors — light theme
| Token | Value | Use |
|---|---|---|
| `--bg` | `#faf7f2` | page background |
| `--sidebar` | `#554C44` | top nav (Register) / left sidebar (Studio) |
| `--surface` | `#ffffff` | cards, panels, inputs |
| `--surface2` | `#f0ece3` | chips, subtle fills |
| `--border` | `rgba(36,31,26,.08)` | card/panel borders |
| `--divider` | `rgba(36,31,26,.06)` | inner dividers |
| `--input-border` | `rgba(36,31,26,.16)` | input/control borders |
| `--text` | `#241f1a` | primary text |
| `--muted` | `#6b6259` | secondary text |
| `--faint` | `#a39a8c` | captions, placeholders |
| `--accent` / `--accent-text` | `#A82040` | primary brand red — buttons, active, links |
| `--accent-soft` | `rgba(168,32,64,.1)` | active fills |
| `--accent-soft2` | `rgba(168,32,64,.16)` | stronger active fills |
| `--green` | `#2F4034` | success / live / tax-free |
| `--green-soft` | `rgba(47,64,52,.14)` | success fill |

### Colors — dark theme
`--bg` `#201a15` · `--sidebar` `#1b1611` · `--surface` `#2a2119` · `--surface2` `#33291f` · `--border` `rgba(255,255,255,.08)` · `--divider` `rgba(255,255,255,.06)` · `--input-border` `rgba(255,255,255,.15)` · `--text` `#efe9e0` · `--muted` `#a89f92` · `--faint` `#6f685e` · `--accent` `#A82040` · `--accent-text` `#e58ba0` · `--accent-soft` `rgba(168,32,64,.2)` · `--accent-soft2` `rgba(168,32,64,.3)` · `--green` `#8fbf9c` · `--green-soft` `rgba(143,191,156,.16)`.

Theme is applied by setting these CSS custom properties on the app root element and swapping instantly (no reload). Implement as a theme context/provider, not per-component overrides.

### Category / tile color palette (10 presets)
`#A82040` `#C56A1A` `#B8892B` `#4E7A51` `#2E6F7E` `#3B5A8C` `#6B4E8C` `#9C3D5A` `#7A5C3E` `#5A5550`
Each catalog category has a default color from this palette; POS buttons and Register product tiles inherit it. Text color on a colored tile is auto-chosen for contrast (luminance test: `#241f1a` on light tiles, `#ffffff` on dark).

### Typography
- **IBM Plex Sans** — all UI text. Weights 400 / 500 / 600 / 700.
- **IBM Plex Mono** — IDs, prices, timers, totals, time ranges. Weights 400 / 500 / 600.
- **Display / title face — DIVERGES between the two apps (intentional, confirm before unifying):**
  - **Register app** titles/labels use **Public Sans** 700 (screen titles, order title, table labels, sheet headers).
  - **Menu Studio** titles/wordmark/card titles use **Source Serif 4** 600–700.
- Scale: page titles 20–22px; card/section titles 15–17px; body 13–13.5px; captions 10.5–11px uppercase with ~0.08–0.1em tracking.

### Radii / shadows / motion
- Radii: controls 6–12px; cards 10–14px; pills/badges 6–11px; modals 18px; floating bars 11–14px.
- Shadows: cards subtle `0 4px 24px rgba(36,31,26,.06)`; floating dark bars `0 10px 34px rgba(36,31,26,.32)`; modals `0 24px 70px rgba(36,31,26,.4)`; slide-over `-14px 0 40px rgba(36,31,26,.22)`.
- Keyframes (Register app): `zrSlideIn` (slide-over sheet in from right, .22s cubic-bezier(.22,.61,.36,1)); `zrFade` (overlay fade .18s); `zrPop` (scale-in .16–.2s for bars/toasts/cards); `zrPulse` (opacity pulse, available for live indicators).

---

## Register app — screens NOT covered in the other docs

The persistent top nav (Register / Tables / Online + theme toggle + avatar) and the **Tables** screen are documented in `README-tables-floormap.md`. Below are the remaining Register-app screens.

### Screen: Register (order entry)
**Purpose:** staff tap products to build an order, customise items, then take payment.

**Layout** — full content area, `display:flex` with three regions:
- **Header** (`flex:none`, `padding:14px 22px`, `background:--surface`, bottom border): title "Register" (Public Sans 700, 20px) + uppercase subtitle "Café — All Day · Main" (IBM Plex Sans 500, 10.5px, `.09em` tracking, `--faint`).
- **Category rail** — `width:200px`, `background:--surface`, right border, vertical list. One row per category; the active category row is filled with its category color (contrast text), others are plain. Rows ellipsize long names. Hover: `filter:brightness(1.06)`.
- **Product grid** — `flex:1`, scrolls, `padding:18px 20px`, `background:--bg`. CSS grid `repeat(auto-fill,minmax(180px,1fr))`, `gap:14px`. Each product **tile**:
  - Colored fill from its category color (contrast text). Rounded, hover lifts (`translateY(-1px)` + brightness).
  - Two tile variants: **text-only** (name + mono price) and **with-image** (name/price header strip, then a full-bleed `object-fit:cover` photo below; only the "Latte" sample has one, via `uploads/images.jpg`).
  - If the product has a modifier set, a small **"+" badge** appears top-right (semi-transparent chip) signalling it opens the customise sheet.
- **Order pane** — `width:clamp(320px,25vw,380px)`, `flex:none`, `background:--surface`, left border, column:
  - **Header:** circular ticket-number chip (mono, accent-soft bg), order title + subtitle, and a ✕ "clear order" button. Below: an **order-type segmented control** (pill group in a `--surface2` track, `border-radius:11px`): Dine-in / Takeaway / etc. — active segment filled.
  - **Line list** (scrolls): empty state = centered 🧾 + "No items yet." Each line row: a left color bar (category color), item name + line total (mono), any chosen modifiers as `· modifier` sub-lines (muted), a **qty stepper** (− value +), and unit "…​ ea" price. Tapping a line selects it.
  - **Totals footer:** Subtotal, "GST (incl. 10%)", then a bold **Total** (Public Sans 700 label + 22px mono value). Actions row: **Hold** (outline) + **Pay $NN.NN** (accent fill, `flex:1`, 48px tall).

### Screen: Online (delivery & pickup queue)
**Purpose:** monitor and progress online orders across channels.

**Layout** — header (title "Online Orders" + subtitle "Delivery & Pickup Channels", right-aligned channel legend with colored swatches), then a **3-column board** filling the area (`display:flex; gap:18px`, columns don't scroll as a page — each column body scrolls). Columns: **New**, **Preparing**, **Ready** (kanban-style).
- **Column** — `flex:1`, `background:--surface`, bordered, `border-radius:14px`. Header: status dot + uppercase title + a count pill (mono, `--surface2`). Body scrolls, `gap:12px`; empty column shows "Nothing here".
- **Order card** — bordered, `background:--bg`, `zrPop` entrance. Top row: **channel chip** (colored per channel — Uber Eats / DoorDash / Web), mono order id, and a **timer chip** (e.g. "2 min ago", "8 min left", "Ready"). Then customer name (600 13.5px), an items summary line "N items · $total" (mono total), and a dashed-top **item detail** block (line-by-line). Actions vary by status:
  - **New** → **Reject** (outline) + **Accept** (green `#2F4034` fill).
  - **Preparing** → **Mark ready** (accent fill).
  - **Ready** → **Picked up ✓** (outline).
- The top-nav **Online badge** (accent pill counter) reflects the number of `new` orders.

### Component: Modifier customise sheet
Opens when a product with a modifier set is tapped. Right-hand **slide-over** (`clamp(380px,34vw,460px)`, `zrSlideIn`) over a dimming overlay (`rgba(36,31,26,.42)`, `zrFade`).
- **Header:** a color square (product color), product name (Public Sans 700, 19px), "$base · Customise" subtitle, ✕ close.
- **Body (scrolls):** one block per modifier group. Group header = uppercase group name + a **rule chip** ("Choose 1" / "Optional"). Choices are tappable rows with a selection **mark** (radio-style for single-select groups, checkbox-style for multi), label, and a `+$X.XX` price (mono) when the option costs extra. Row hover highlights the accent border.
- **Footer:** a **qty stepper** (− value +, 44px tall) + a full-width **"Add to order  $total"** accent button (total updates live with selections × qty).
- Selection rules: single-select groups default to the first option and always keep exactly one; multi-select toggle freely. Adding pushes a distinct order line (modified items are never merged with plain ones).

### Component: Payment flow
Opens from **Pay** in the order pane. Centered **modal** (`clamp(440px,44vw,560px)`, `border-radius:18px`, `zrPop`) over a `rgba(36,31,26,.5)` overlay. Two states:

**Choosing:**
- Header: "Amount due" label + large mono total; ✕ close.
- **Method tabs:** 💳 Card / 💵 Cash (active tab emphasized).
- **Card:** dashed terminal placeholder (📟) + "Present card or device to the terminal", then a full-width **Charge $total** accent button.
- **Cash:** a 3-column grid of **tender presets** (quick cash amounts), a **Tendered / Change** summary panel (change updates live; turns/greys based on whether tendered covers the total), and a **Complete payment** button (enabled only when tendered ≥ total).

**Done (success):** green ✓ circle, "Payment complete", method + amount line, a **Change due** panel (large green mono) when cash change applies, and a **New order** accent button that resets the order.

### Toast
Global, bottom-center dark pill (`zrPop`, auto-dismiss ~1600ms) for transient confirmations ("Latte added", "Merged T3 + T4", etc.).

---

## Register-app state (suggested shape)
From the prototype `Component` class:
- `theme` `'light'|'dark'`; `screen` `'register'|'tables'|'online'`.
- `orderType`, `activeCat`, `order[]` (lines: `{id,pid,name,cat,unit,qty,mods[]}`), `selLine`, `seq`, `ticket` (ticket number).
- `mod` — active modifier-sheet state `{prod, sets, sel[][], qty}` or null.
- `pay` — payment state (method, tendered, done flag) or null.
- Tables: `tables` (status seed grouped by zone), `selTable`, `activeFloor` (`'main'|'rooftop'`), `mergeAnchor`, `merges` (bidirectional id→partner map). See `README-tables-floormap.md` for the full model.
- `online[]` — order cards `{id,status:'new'|'prep'|'ready',ch,customer,items[],total,timer}`.
- `toast` — transient message or null.

**Data reference (all placeholder):** `CATS` (6 categories), `PRODUCTS` (~44 items with category/price/modifier-set ref), `MODSETS` (modifier group definitions per set: `coffee`, `brekky`, `avo`, `roll`), `FLOORS` (floor layouts), `initTables()` / `initOnline()` seeds. Real build should compute timers from timestamps and persist orders/tables to a backend.

## Assets
Only one raster asset (`uploads/images.jpg`, a product photo). All other imagery is CSS shapes, inline SVG (nav icons — see `README-tables-floormap.md` for exact paths), or Unicode glyphs (✕ − + ✓ 🧾 💳 💵 📟 ◷ ⛓ ☾ ☀). Fonts load from Google Fonts (Public Sans, Source Serif 4, IBM Plex Sans, IBM Plex Mono).
