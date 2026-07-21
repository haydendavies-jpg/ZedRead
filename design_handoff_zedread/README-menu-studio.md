# Handoff: Menu Studio (POS Menu & Layout Management)

## Overview
"Menu Studio" is the admin surface for a café/restaurant POS system. It lets a manager maintain the product/pricing catalog (Products, Modifiers, Categories), assign categories to reporting groups, design one or more POS button layouts (the on-register grid of buttons staff tap to ring up items), and manage published Menus with scheduling. A companion exploration file documents the "modifier comboing" interaction (an option inside one modifier group that expands a linked, nested modifier group).

## About the Design Files
The files in this bundle (`ZedRead Menu Studio.dc.html`, `Modifier Comboing Options.dc.html`) are **design references built in HTML** — interactive prototypes showing intended look, structure, and behavior. They are **not production code to copy directly**. The task is to **recreate these designs in the target codebase's existing environment** (React, Vue, native, etc.) using its established component patterns, state management, and data layer — or, if no frontend environment exists yet, to choose the most appropriate framework and implement the designs there.

To view a file, open it directly in a browser (each is a self-contained HTML document).

## Fidelity
**High-fidelity.** Colors, typography, spacing, and most interactions (selection, drag, expand/collapse, popovers) are intended to be final or near-final. Treat exact hex values, font sizes, and spacing in this doc as authoritative unless the target design system dictates otherwise — flag conflicts rather than silently overriding.

Data shown (product names, prices, categories, menu names/dates) is **placeholder/sample data** for the mockup only — wire up to real data in implementation.

---

## Global layout & navigation

- Two-pane app shell: a fixed **left sidebar** (220px) with brand wordmark, primary nav (Dashboard, Orders, Menus, Menu Studio, Reporting, Payment Summary), an "Admin" section (Manage Catalog, Blackout Dates, Invite Users, Manage Users), and a user/account footer row with a light/dark theme toggle.
- Right side is the **content area**, full remaining width, its own vertical scroll per screen.
- Brand mark: previously an icon + "ZedRead" wordmark; **the icon has been removed pending a final logo decision** — currently just the wordmark. Leave a slot for a future logo mark to the left of the wordmark.
- A light/dark theme toggle (moon/sun icon, bottom-left) swaps a full CSS custom-property palette (see Design Tokens). Implement as a theme context/provider, not per-component overrides.

### Top-level nav destinations relevant to this bundle
- **Menu Studio** — the main screen documented below (Table / POS Layout toggle).
- **Menus** — a separate top-level table of published "Menus" (a menu = a saved configuration of products/prices/availability), with scheduling.

---

## Screen: Menu Studio — Table view

### Purpose
Manage the underlying catalog: Products, Modifiers (option sets), and Categories.

### Layout
- Top bar: page title "Menu Studio" + subtitle ("Café — All Day · Main Kitchen"), a segmented control ("Table" / "POS Layout"), and right-aligned actions: save-state indicator ("● Saved", green dot), History, Export, Import pills, and a primary **"Publish"** button (accent fill, was previously labeled "Push to Register").
- Sub-header: three tabs — **Products** (count badge), **Modifiers** (count badge), **Categories** (count badge) — plus a search input, an "Archived…" pill, and a primary "+ New …" action (label changes per tab).

### Products tab
- Data grid, one sticky header row + N data rows. Columns (grid-template-columns `38px 0.85fr 1.55fr 1fr 1fr 0.7fr 0.85fr 1.35fr 46px`):
  1. row checkbox
  2. Product ID (mono font, muted)
  3. Product name (medium weight)
  4. Category — pill with a small colored dot (category's default color, see Categories) + category name
  5. Reporting group — dropdown-style cell (chevron)
  6. Price — right aligned, tabular numerals
  7. Tax — dropdown-style cell; "Free" renders in green, otherwise "GST 10%"
  8. Modifiers — dashed "empty" box if none, solid bordered "filled" box listing option-set name(s) if present
  9. delete icon (trash), muted, only on row hover emphasis
- Row height 52px, hover state = faint background tint over the whole row.

### Modifiers tab (option sets)
- 4-column responsive card grid, one card per modifier/option-set, plus a trailing dashed "+ New option set" ghost card.
- Each card:
  - Header: modifier name (serif, 16px, 600) + duplicate/delete icons.
  - Meta row: Required toggle (checkbox + label), Min stepper value, Max stepper value (both shown as small bordered numeric chips, not live steppers, in this view).
  - Options list (rows): drag handle (⠿), option name, price (`+$` prefixed bordered input), delete (✕).
  - **Comboing**: an option can link to one or more other modifier groups ("linked groups"). When an option has links, it shows a small pill chip: link icon + link count (e.g. `🔗 2`) with a chevron. Clicking the chip **expands/collapses** an indented nested block directly under that option row showing each linked group: a "↳ Linked" tag, the linked group's name, its selection rule (e.g. "choose 1"), and its own option rows (name + price). A "+ Link another group" ghost action sits at the bottom of the expanded block. This is a collapsible **inline nested cascade** — see `Modifier Comboing Options.dc.html` for the fuller exploration of this pattern (three alternatives were explored; **this inline-nested-cascade approach, "option 1", was the one chosen**). Only one visual indent level is shown in this mock (a linked group is not itself shown expanding into further linked groups), but the data model should support arbitrary nesting if the product requires it later — confirm with design before building deeper recursion.
  - Footer strip: "▸ Used by N products" (muted, small).
  - "+ Add option" ghost link under the list.

### Categories tab
- Purpose: assign each category a **reporting group** and a **default button color** (the color POS layout buttons default to). Categories not yet assigned to any reporting group are shown, not hidden.
- Layout: single column, max-width ~680px, centered.
  - Header row: helper copy ("Each category has a default button colour…"), a "+ Reporting group" button (inline creation, see below), and a "Select all" checkbox+label.
  - Inline **add form**: when creating a category or a reporting group, an inline bordered form appears above the groups (accent border), with a text input for the name, and — only when adding a category — a `<select>` to optionally assign it to a reporting group at creation time (default "Unassigned"). Cancel / Confirm actions.
  - **Grouped cards**: one card per reporting group (in the order groups were created/used), each with:
    - Header row: group select-all checkbox, group name tag, "reporting group" label, category count.
    - Rows: one per category — row checkbox, a **color swatch** (click opens a popover: a curated palette of ~10 preset swatches + a native color-picker "Custom…" input, live-updating the swatch), category name, product count, and a small "reporting group" pill on the right showing its current group (click intended to reassign — implement as its own dropdown if needed).
  - An **"Unassigned"** card always renders first when any categories lack a reporting group, styled identically to a real group card, so ungrouped categories are never hidden.
  - **Bulk assign**: selecting 1+ category rows (via row or group checkboxes) reveals a floating bottom bar (dark, rounded, centered, sticky to viewport bottom) showing "{N} selected", an "Assign to reporting group ▾" button that opens a small dropdown menu (one item per reporting group, each showing current member count, plus an "Unassign" item at the bottom), and a "Clear" link.

---

## Screen: Menu Studio — POS Layout

### Purpose
Design the button grids staff tap on the physical/virtual register. A restaurant can have **several POS layouts** (e.g. "Café — All Day", "Breakfast", "Lunch", "Happy Hour"), each visible on the register only during its configured active hours/days.

### POS Layouts list (landing view when "POS Layout" is selected)
This is the entry point — clicking "POS Layout" in the segmented control shows a **table of layouts to choose from**, not the grid editor directly.
- Header: helper copy, and actions: **Import** (pill), **Schedule publish** (pill — schedules a bulk publish of POS changes for a future date/time; opens an inline date-time bar with Cancel/Confirm), **+ New layout** (primary).
- Table columns: Layout (color dot + name + button count), Status (pill: "Published" green / "Unpublished" neutral), Active time (bold mono time range e.g. `7:00 AM – 11:00 AM`, or "All day", plus a day-of-week chip e.g. "Every day" / "Mon–Fri" / "Sat–Sun"), Last published (date + time, or "—"/"never published"), Last edited (date + time), Actions (**Edit** primary, **Duplicate**, **Export**).
- Clicking a row (or "Edit") opens the grid editor for that layout. A "‹ Layouts" breadcrumb link at the top of the editor returns here.
- **Active time/days is a first-class scheduling concept**: each layout has a start time, end time (or "all day"), and a day-of-week rule. The POS should show/hide each layout automatically based on current time matching this window — this is distinct from the "Schedule publish" action (which schedules *when edits go live*, not when the layout is *visible* to staff).

### Grid editor (per layout)
- Left rail, labeled **"Tabs"**: one entry per top-level tab/page in this layout (color dot, name, button count), the active one highlighted; **"+ Add tab"** creates a new one. Helper copy at the bottom explains selection/drag gestures.
- Center: breadcrumb (back-to-Layouts link, then the tab path — supports drilling into a tab-inside-a-tab), header actions **"+ Tab"** (nested tab inside the current one) and **"+ Row"** (append a row of empty slots), then the button grid itself.
- **Grid**: CSS grid, 6 columns, 92px auto row height, `grid-auto-flow: dense` so buttons need not be sequential — a button can span multiple columns/rows and the grid packs around it. Empty cells render as a dashed "+" placeholder tile (click to fill with a product).
- **Button (tile) states**:
  - Normal: colored fill (from linked product's category default color, or an explicit override), label, price, and — for folder/tab tiles — an item-count and an "open" (⤢) icon.
  - Selected: colored ring/outline + a small circular checkmark badge (top-right) + a resize handle (⟌, bottom-right corner) appears.
  - Multi-selected (2+): same but no per-tile resize handle; a bottom action bar appears instead (see below).
- **Selection**: click selects one (and clicking empty space / re-clicking the sole selection clears it); shift/⌘/ctrl-click adds/toggles others into the selection.
- **Drag**: pressing and dragging a selected tile (or a tile that becomes selected on press) shows a small dark "Moving N button(s)" ghost label following the pointer; dropping onto a **tab tile** or a **rail entry** moves the selected tiles into that tab's grid. Implement via pointer events (down/move/up), not native HTML5 DnD, to support the ghost label and cross-region (rail vs. grid) drop targets.
- **Grid drag-resize**: dragging a selected tile's corner handle changes its column/row span live (min 1×1, max observed 6 wide × 4 tall — grid is 6 columns).
- **Multi-select action bar** (bottom, floating, dark pill bar): color swatches (same curated palette as Categories) to bulk-recolor, a custom color-picker swatch, a "Move to ▾" dropdown (lists sibling tabs + all top-level layout tabs/pages as targets — same effect as drag/drop), "Group into tab" (bundles the selection into a newly created nested tab), "Delete", and "Clear".
- **Inspector** (right panel, shown only on a *single* selection): live preview tile; for a product button — a "linked product" dropdown (choose which catalog product this button represents) and its category, read-only; for a tab/folder button — a rename text input and an "Open tab ⤢" shortcut; for all buttons — the color palette + custom picker + (product buttons only) a "Category default" quick-reset link; and a width/height stepper pair (with the same min/max as drag-resize) plus a "Delete button" action at the bottom.

---

## Screen: Menus (top-level nav item, separate from Menu Studio)
A menu = a full saved configuration (distinct from a POS layout, which is the button arrangement) that can be assigned to registers/channels and published on a schedule.
- Header: title, subtitle (menu count), Import pill, "+ New menu" primary.
- Table columns: Menu (name + short note, e.g. daypart or purpose), Status (pill: Live/green, Scheduled/orange, Draft/neutral — plus, when scheduled, a plain-text "scheduled for" timestamp next to the pill), Assigned to (which registers/channels), Products (count), Updated (relative time), Actions.
- Row actions vary by status: **Draft** → "Publish" (primary) + "◷ Schedule" (opens inline date-time row directly under that row, with Cancel / "Schedule publish" confirm). **Scheduled** → "Publish now" (primary) + "Cancel" (reverts to Draft). All rows also get "⧉ Duplicate" and "⤓ Export".

---

## Interactions & Behavior summary
- Segmented control (Table/POS Layout) and tab strips: simple active-state swap, no route change needed unless the target app uses routing — either is fine.
- All popovers (color picker, dropdown menus) should close on outside click / selecting an item; only one open at a time.
- Inline "add" forms (new category, new reporting group) replace themselves with the created item and reset on confirm; Cancel discards the draft without side effects.
- Bulk bars (Categories bulk-assign, POS multi-select) are position:sticky/fixed to the bottom of their scroll container, centered, and only render when the selection is non-empty.
- Theme toggle affects the whole app instantly (CSS variables), no reload.
- No client-side persistence is implemented in the mock (in-memory React-like state only) — the real app should persist catalog/category/layout/menu edits to a backend, including autosave/"Saved" indicator semantics.

## State Management (suggested shape)
- `theme`: 'light' | 'dark'
- `screen`: 'studio' | 'menus'; within studio: `layout`: 'table' | 'pos'; within table: `tab`: 'products' | 'modifiers' | 'categories'
- `categories[]`: { name, count, color, reportingGroupId | null }
- `reportingGroups[]`: { id, name }
- `modifiers[]`: { name, required, min, max, usedByCount, options: [{ name, price, linkedGroupIds[] }] }
- `posLayouts[]`: { id, name, color, status: 'published'|'unpublished', activeTime: { allDay, start, end, days }, lastPublishedAt, lastEditedAt, tabs: [ { id, name, color, tiles: [ { id, kind:'product'|'folder'|'empty', label, price, categoryId, color?, w, h, tiles? (if folder) } ] } ] }
- `menus[]`: { id, name, note, status: 'published'|'scheduled'|'draft', assignedTo, productCount, updatedAt, scheduledAt }
- Selection state: `selectedCategoryIds`, `selectedTileIds`, plus current tab-drill path for POS editing (array of folder ids from the layout root).
- Combo/linked-group expand state: a set/map of currently expanded option keys (per modifier card).

## Design Tokens

### Colors (light theme)
- `--bg` #faf7f2 (page background)
- `--sidebar` #f4efe4
- `--surface` #ffffff (cards, inputs)
- `--surface2` #f0ece3 (chips, subtle fills)
- `--border` rgba(36,31,26,.08)
- `--divider` rgba(36,31,26,.06)
- `--input-border` rgba(36,31,26,.16)
- `--text` #241f1a
- `--muted` #6b6259
- `--faint` #a39a8c
- `--accent` / `--accent-text` #A82040 (primary brand red — buttons, active states, links)
- `--accent-soft` rgba(168,32,64,.1) / `--accent-soft2` rgba(168,32,64,.16) (active tab/nav fills)
- `--green` #2F4034 (success/live/tax-free states)
- Category/tile preset palette (10 swatches): `#A82040 #C56A1A #B8892B #4E7A51 #2E6F7E #3B5A8C #6B4E8C #9C3D5A #7A5C3E #5A5550`

### Colors (dark theme)
- `--bg` #201a15, `--sidebar` #1b1611, `--surface` #2a2119, `--surface2` #2a251f
- `--border` rgba(255,255,255,.07), `--divider` rgba(255,255,255,.05), `--input-border` rgba(255,255,255,.14)
- `--text` #efe9e0, `--muted` #a89f92, `--faint` #6f685e
- `--accent` #A82040, `--accent-text` #e58ba0, `--accent-soft` rgba(168,32,64,.18), `--accent-soft2` rgba(168,32,64,.26)
- `--green` #8fbf9c

### Typography
- Display/serif (titles, card titles, wordmark): **Source Serif 4**, weight 600–700.
- UI (everything else): **IBM Plex Sans**, weights 400/500/600/700.
- Mono (IDs, prices, stepper values, time ranges): **IBM Plex Mono**, weights 400/500.
- Base UI text ~13–13.5px; table/list body ~13.5px; section captions 10.5–11px uppercase with ~0.1em tracking; card titles 15–16px; page titles 22px.

### Spacing / radii / shadows
- Standard control radius: 6–7px; cards 10px; pill/segmented controls 6–8px; circular avatar/dot as needed.
- Card border: 1px solid `--border`. Dividers: 1px solid `--divider`.
- Bulk action bars: 11px radius, `box-shadow: 0 8px 30px rgba(36,31,26,.28)` (dark bar), dropdown menus `0 12px 34px rgba(36,31,26,.22)`.
- Grid gap 10px; POS tile row height 92px.

## Assets
No external image/icon assets — all icons are Unicode/text glyphs (e.g. ◆ ▤ ▦ ▣ ▥ $ ⚙ ▧ ✉ ◈, ⌕, ⌄, 🔗, ⠿, ⧉, ✕, ⟌, ⤢, ◷, ⤓, ⤒). Fonts loaded from Google Fonts (Source Serif 4, IBM Plex Sans, IBM Plex Mono). The sidebar previously had a circular brand mark (letter "Z" in a ringed circle) — **this has been intentionally removed pending a final logo decision**; leave space to drop one in next to the "ZedRead" wordmark once chosen. Two other files in the project (`ZedRead Logo Concepts.dc.html`, `ZedRead Palette Options.dc.html`) contain exploratory logo/color directions not yet finalized and are not included in this bundle — ask if you need them.

## Files
- `ZedRead Menu Studio.dc.html` — the full design: sidebar/app shell, Menu Studio (Table: Products/Modifiers/Categories; POS Layout: layouts list + grid editor), and the Menus table screen. Open directly in a browser to explore interactions.
- `Modifier Comboing Options.dc.html` — earlier-stage exploration of the modifier "comboing" (linked option groups) interaction pattern; shows the option that was ultimately chosen (inline nested cascade, integrated into Menu Studio) alongside alternatives that were not used. Reference for intent/rationale only.
