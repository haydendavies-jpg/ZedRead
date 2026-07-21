# Handoff: ZedRead Register — Tables (Front of House)

## Overview
ZedRead Register is a hospitality POS. This handoff covers the **Tables / Floor Map** screen and its supporting top navigation. It shows a live floor plan of a venue with per-table status, occupancy, timers, reservations, multi-floor switching, and a table-merge action.

## About the Design Files
The file in this bundle (`ZedRead Register.dc.html`) is a **design reference created in HTML** — a prototype showing intended look and behavior, NOT production code to copy directly. The task is to **recreate this design in the target codebase's existing environment** (React, Vue, SwiftUI, native, etc.) using its established patterns, component library, and design tokens. If no environment exists yet, pick the most appropriate framework and implement there.

Note: the HTML prototype is a single-file "Design Component" spanning the whole POS (Register, Tables, Online screens). This handoff documents ONLY the Tables screen and top nav — the other screens are context.

## Fidelity
**High-fidelity.** Colors, typography, spacing, and interactions are final. Recreate pixel-close using the codebase's libraries. Exact hex values, fonts, and sizes are listed below.

## Screens / Views

### Top Navigation Bar (persistent)
- **Purpose:** Switch between Register / Tables / Online; theme toggle + user avatar.
- **Layout:** Fixed 64px-tall horizontal bar. `background: #554C44` (var `--sidebar`). Padding `0 18px`, `display:flex; align-items:center; gap:8px`.
- **Components:**
  - **Logo tile** — 40×40, `border-radius:11px`, `background:rgba(255,255,255,.14)`, serif "Z" (Source Serif 4, 700, 21px, #fff).
  - **Nav items** (Register / Tables / Online) — flex row, `gap:5px`, `margin-left:8px`. Each: `padding:10px 20px; border-radius:12px; gap:9px; font:600 14px 'IBM Plex Sans'; color:#fff`. Active item has a lighter fill; hover `background:rgba(255,255,255,.1)`.
  - **Nav icons** — inline 18×18 SVGs, `stroke:currentColor; stroke-width:1.9; fill:none; stroke-linecap:round; stroke-linejoin:round`:
    - Register (receipt): `<path d="M5 3h14v18l-2.5-1.6L14 21l-2-1.4L10 21l-2.5-1.6L5 21z"/><path d="M9 8h6M9 12h6"/>`
    - Tables (table w/ chairs): `<rect x="7" y="7" width="10" height="10" rx="2"/><path d="M2 10v4M22 10v4M10 2h4M10 22h4"/>`
    - Online (globe): `<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.6 3 2.6 15 0 18M12 3c-2.6 3-2.6 15 0 18"/>`
  - **Online badge** — pill counter, `min-width:20px; height:20px; border-radius:10px; background:#A82040; color:#fff; font:700 11px 'IBM Plex Sans'`.
  - Right side: theme toggle (☾/☀) + circular avatar "M".

### Tables / Floor Map
- **Purpose:** Front-of-house sees live table state at a glance, selects a table to act on it, merges tables, and switches between floor maps.
- **Layout:** Column filling the content area. `background:#faf7f2` (`--bg`).
  - **Header** (`flex:none`) — `display:flex; align-items:center; gap:16px; padding:14px 24px; border-bottom:1px solid rgba(36,31,26,.08); background:#fff`.
    - Title block: "Table Map" (Source Serif 4, 700, 20px, #241f1a) + subtitle "FRONT OF HOUSE · LIVE" (IBM Plex Sans, 500, 10.5px, uppercase, letter-spacing .09em, #a39a8c).
    - **Floor tabs** (`margin-left:22px; display:flex; gap:6px`) — one per floor. Each: `padding:7px 15px; border-radius:9px; font:600 12.5px 'IBM Plex Sans'; border:1.5px solid`. Active: `background:#241f1a; color:#fff; border-color:#241f1a`. Inactive: `background:transparent; color:#6b6259; border-color:rgba(36,31,26,.14)`.
    - Spacer (`flex:1`), then **legend** (flex row gap:16): swatch 12×12 `border-radius:4px` + label (IBM Plex Sans 500 12px #6b6259). Statuses: Open, Seated, Ordered, Needs bill.
  - **Map canvas** — scroll area, `padding:24px`. Inner stage: `position:relative; width:100%; max-width:1220px; aspect-ratio:16/10; margin:auto; background:#fff; border-radius:22px; box-shadow:inset 0 0 0 2px rgba(36,31,26,.08), 0 4px 24px rgba(36,31,26,.06)`.
      - **Zone backdrops** — absolutely positioned rects (% coords) with tint fill; dashed border for outdoor zones (`2px dashed rgba(36,31,26,.18)`) else `1.5px solid rgba(36,31,26,.08)`; `border-radius:16px`. Zone label top-left: IBM Plex Sans 700 10.5px uppercase, letter-spacing .12em, #a39a8c.
      - **Table tiles** — absolutely positioned by % (`transform:translate(-50%,-50%)`). Shapes: stool 58×58 circle, round 92×92 circle, rect 154×94 (`border-radius:18px`). `border:2.5px solid <status border>`; fill `#fff` when open else status tint; `box-shadow:0 2px 8px rgba(36,31,26,.12)`. Hover: `scale(1.04)`. Merge-anchor tile: red border `#A82040` + `box-shadow:0 0 0 3px rgba(168,32,64,.25), …`.
        - Tile content: label (Source Serif 4 700 15px), covers/seats line "2/4" or "Open" (IBM Plex Sans 600 10px), and for occupied a seated timer "24m" (IBM Plex Mono 600 9px, opacity .85).
        - **Total badge** (occupied) top-right `-8px`: IBM Plex Mono 700 9.5px, #fff on status accent, `padding:2px 6px; border-radius:8px`.
        - **Reservation badge** (open tables with booking) top-left `-9px`: "◷ 7:30", IBM Plex Sans 700 8.5px, #241f1a on #f0ece3, `border:1.5px solid rgba(36,31,26,.15)`.
        - **Merge badge** (merged tables) bottom-center `-9px`: "⛓ T2", IBM Plex Sans 700 8.5px, #fff on #241f1a.
      - Decorative: bar-counter strip (top-left) and an "Entrance" marker (bottom-center) with a `#A82040` accent line.
  - **Selection bar** (appears on table select) — `position:absolute; left:50%; bottom:22px; transform:translateX(-50%)`. `display:flex; align-items:center; gap:18px; background:#241f1a; color:#fff; border-radius:14px; padding:12px 18px; box-shadow:0 10px 34px rgba(36,31,26,.32); max-width:min(94vw,1000px); animation:zrPop .16s ease`.
      - Left: table label "Indoor · T3" (Source Serif 4 700 16px) + status pill (700 8.5px uppercase, #fff on status accent, `padding:2px 7px; border-radius:6px`).
      - Divider (1px × 36px, `rgba(255,255,255,.16)`).
      - **Detail chips** (flex gap:18) — each a stacked pair: uppercase key (IBM Plex Sans 600 8px, letter-spacing .1em, `rgba(255,255,255,.5)`) over value (600 13px). For occupied: Guests "4 / 4", Seated "41m", Last touch "3m" (value turns `#F4A98C` when ≥15m), Server, Total. For open: Seats, and Reserved (value `#E9C46A`) if booked.
      - Spacer, then buttons: **Merge** (outline, `border:1.5px solid rgba(255,255,255,.28)`; label "⛓ Merge" → "Cancel merge" when arming; hover `background:rgba(255,255,255,.16)`); **Open order →** (`background:#A82040`, 600 12.5px, `padding:9px 16px; border-radius:9px`); **✕** close.

## Interactions & Behavior
- **Select table:** click a tile → selection bar shows its details. Clicking a floor tab clears the selection.
- **Merge flow:** with a table selected, click **Merge** → that tile becomes the "merge anchor" (red ring) and a toast reads "Tap another table to merge with T3". Clicking any *other* tile records a bidirectional merge (both tiles get a "⛓ <partner>" badge) and toasts "Merged T3 + T4". Clicking **Merge** again while armed cancels (label "Cancel merge"). Close (✕) clears both selection and merge-arming.
- **Floor switch:** clicking a floor tab swaps the map (zones + tiles) and resets selection/merge.
- **Toast:** dark pill, bottom-center, auto-dismiss after 1600ms.
- **Hover:** tiles scale 1.04 (transition .1s); buttons brighten.
- **Theme:** light/dark via CSS custom properties on the root (see tokens).

## State Management
- `activeFloor` — key of current floor map ('main' | 'rooftop'). Default 'main'.
- `selTable` — currently selected table object (`{id, status, covers, seats, total, server, activated, touch, reserved, zone}`) or null.
- `mergeAnchor` — table id armed for merge, or null.
- `merges` — map `{ id: partnerId }` (bidirectional entries) recording merged pairs.
- `tables` — source status data grouped by zone (see Data below); joined by id to the floor **layout** map for rendering.
- `toast` — transient message string.
- `theme` — 'light' | 'dark'.

Rendering joins two structures by table id: **layout** (position % + shape, per floor) and **status data** (occupancy/timers/reservation, flat list). Timers (`activated`, `touch`) are integers = minutes; a real build should compute these from timestamps.

## Data Model

### Floor layouts (position + shape), keyed by floor
Each floor: `{ label, zones:[{label,x,y,w,h,tint,dashed}], tables:{ ID:{x,y,shape} } }` where x/y/w/h are % of the stage; shape ∈ stool | round | rect.
- **main** ("Ground Floor") — zones: Bar, Indoor Dining, Patio(dashed). Tables: B1–B4 (stool), T1–T6 (round; T6 rect), P1–P5 (round; P5 rect).
- **rooftop** ("Rooftop") — zones: Rooftop Bar, Deck(dashed), Lounge. Tables: RB1–RB3 (stool), R1–R4 (round), L1/L2 (rect), L3 (round).

### Table status (occupancy), joined by id
`{ id, status, covers, seats, total, server, activated(min), touch(min), reserved }`. Statuses: `open` (no covers; may carry `reserved:"7:30 · Chen"`), `seated`, `ordered`, `bill`. See the HTML `initTables()` for the full seed set (~24 tables across Indoor/Patio/Bar/Rooftop groups).

## Design Tokens

### Colors (light)
- `--bg` #faf7f2 · `--surface` #fff · `--surface2` #f0ece3 · `--sidebar` #554C44
- `--text` #241f1a · `--muted` #6b6259 · `--faint` #a39a8c
- `--border` rgba(36,31,26,.08–.1) · `--input-border` rgba(36,31,26,.18)
- Accent / primary action: #A82040
- **Status:** Open — dot #f0ece3, accent #a39a8c · Seated — #3B5A8C (fill rgba(59,90,140,.08), border rgba(59,90,140,.4)) · Ordered — #C56A1A (fill/​border .08/.4) · Needs bill — #A82040 (fill rgba(168,32,64,.08), border .42)
- Alerts in dark bar: stale touch #F4A98C, reserved value #E9C46A
- Dark theme: `--bg` #201a15, `--sidebar` #1b1611, `--surface` #2a2119, `--surface2` #33291f, `--border` rgba(255,255,255,.08).

### Typography
- **Source Serif 4** (700) — table labels, titles.
- **IBM Plex Sans** — UI text, weights 500/600/700.
- **IBM Plex Mono** — numeric badges/timers.

### Radius & shape
- Tiles: circle (stool/round) or 18px (rect). Zones 16px. Nav items 12px. Buttons/tabs 9px. Badges 6–8px. Stage 22px. Logo 11px.
- Tile sizes: stool 58, round 92, rect 154×94.

### Shadows
- Tile `0 2px 8px rgba(36,31,26,.12)`; selection bar `0 10px 34px rgba(36,31,26,.32)`; stage inset ring + `0 4px 24px rgba(36,31,26,.06)`.

### Animation
- `@keyframes zrPop` — small pop/scale-in for the selection bar (~.16s ease). Tile hover transform .1s.

## Assets
No external raster assets. All icons are inline SVG (paths above) or Unicode glyphs (◷ reservation, ⛓ merge, ☾/☀ theme). Fonts from Google Fonts: Source Serif 4, IBM Plex Sans, IBM Plex Mono.

## Files
- `ZedRead Register.dc.html` — the full prototype. Tables screen lives under the `isTables` section of the template; floor layouts in the `FLOORS` const; status seed in `initTables()`; render logic (`floorTables`, `floorZones`, `floorTabs`, `selChips`) and handlers (`tapTable`, `startMerge`, `clearTable`) in the `Component` class `renderVals()`.
