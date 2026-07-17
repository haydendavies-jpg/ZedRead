# ZedRead Portal Design Guide (v1.0)

Authoritative reference for portal colour + table standards, adopted across **both**
the SuperAdmin (admin) and Management portals. Derived from
`ZedRead_Portal_Design_Guide.html` (the high-fidelity mockup in this folder) and the
Menu Studio redesign it standardises.

> **If this file and the code ever disagree, the code wins — flag the conflict.**
> The tokens and classes below are implemented in `src/index.css`; this doc explains
> intent and how to reuse them.

---

## 1. Colour tokens

Every surface reads CSS custom properties (`--zr-*`), never hard-coded hex. That is
what makes the light/dark toggle instant and consistent. Light values live on
`:root`; the `.dark` block (toggled on `<html>` by `ThemeContext`) swaps the whole
set wholesale. **Never hand-tune an individual dark colour per screen — change the
token.**

| Token | Light | Dark | Usage |
|---|---|---|---|
| `--zr-accent` | `#554c44` | `#554c44` | Primary actions, active nav, totals — same warm taupe in both themes |
| `--zr-accent-text` | `#403933` | `#c2b6a8` | Accent-toned **text** (links, active tab/pill labels) on the normal canvas — lighter taupe in dark mode for legibility. NOT for text on a solid accent fill — that stays hardcoded white (`.zr-action--pri`, primary buttons) regardless of theme. |
| `--zr-green` | `#2f4034` | `#8fb89a` | Live / published / paid |
| `--zr-text` | `#241f1a` | `#efe9e0` | Primary ink |
| `--zr-muted` | `#6b6259` | `#a89f92` | Secondary text |
| `--zr-faint` | `#a39a8c` | `#8a8177` | Captions, table-header labels |
| `--zr-sidebar` | `#554c44` | `#332e29` | Sidebar surface — a solid accent-toned colour in **both** themes (darker in dark mode so it doesn't glow against the dark canvas), not a light/dark-toggling parchment/ink pair. Sidebar text/hover/active/border styling in `Layout.tsx` is therefore fixed light-on-dark and does not follow the app-wide `dark:` variant. |
| `--zr-bg` | `#faf7f2` | `#201a15` | App background / table-header fill |
| `--zr-surface` | `#ffffff` | `#2a2119` | Card / table surface |
| `--zr-surface2` | `#f0ece3` | `#2a251f` | Inset / hover surface |
| `--zr-accent-soft` | 10% accent | 18% accent | Accent tint backgrounds |
| `--zr-accent-soft2` | 16% accent | 26% accent | Stronger accent tint |
| `--zr-border` | `rgba(36,31,26,.08)` | `rgba(255,255,255,.08)` | Card / table outer border |
| `--zr-header-border` | `rgba(36,31,26,.10)` | `rgba(255,255,255,.10)` | Under the table header row |
| `--zr-thead` | `#faf9f5` | `#2f2820` | Table header-row fill |
| `--zr-divider` | `rgba(36,31,26,.06)` | `rgba(255,255,255,.06)` | Row + column dividers |
| `--zr-chk` | `#cfc7bb` | `#5a5148` | Unchecked selection checkbox border |
| `--zr-row-hover` | `rgba(36,31,26,.02)` | `rgba(255,255,255,.03)` | Whole-row hover tint |

**Rule of thumb:** paper/parchment carry surfaces; ink/slate/sand carry structure and
secondary UI; warm taupe (`--zr-accent`) is reserved for primary actions, active-nav
states, and totals — never a large background wash. Category / POS-button colours are
the one place a wider palette is allowed (the Menu Studio preset palette); everything
else in the chrome stays on this token set.

Every selection/active state (active tabs, selected table rows, checked checkboxes,
link/option chips, input focus borders, drag drop-target outlines, tile selection
rings) pulls from `--zr-accent` / `--zr-accent-soft` — either directly, or via the
Tailwind `brand-*` scale (`src/index.css` `@theme` block), which is defined from the
same two accent values (`brand-600` = `--zr-accent` = `#554c44`; `brand-700` = the
hover/darker shade `#403933`) so form-level buttons, links, and focus rings never need
a per-component override. `::selection` (browser text-selection highlight) uses the
same `#554c44` in both themes.

### Semantic status colours

Four families only, for badges / pills / dots:

| Family | Meaning | Tokens |
|---|---|---|
| `live` (green) | Live / Published / Paid | `--zr-live-bg` / `--zr-live-fg` |
| `pending` (amber) | Scheduled / Pending / Open | `--zr-pending-bg` / `--zr-pending-fg` |
| `draft` (grey) | Draft / Unpublished / Inactive | `--zr-draft-bg` / `--zr-draft-fg` / `--zr-draft-dot` |
| `void` (red) | Void / Refund / Error / Expired | `--zr-void-bg` / `--zr-void-fg` |

`StatusBadge` (`src/components/StatusBadge.tsx`) maps every status string used in the
portal onto one of these families — use it rather than a bespoke coloured span.

---

## 2. Typography

- **Source Serif 4** (600/700) — page titles and card/section titles only
  (`font-serif` Tailwind token).
- **IBM Plex Sans** (400–700) — every control, label, and body of text. The `.zr-table`
  skin applies it to tables directly.
- **IBM Plex Mono** (400/500) — IDs, prices, time ranges — anything tabular
  (`font-mono` Tailwind token). Pair with `.zr-num` for right-aligned tabular numerics.

> IBM Plex Sans is the global interface font (`body` in `src/index.css`); Source Serif 4
> is applied to titles and the sidebar wordmark via `font-serif`. `Lora` remains only on
> the standalone login page.

---

## 3. Table standard — ONE pattern everywhere

Every data table in the portal reuses one skin. **Do not invent a new row height,
divider colour, or pill shape for a new table — extend this pattern.**

### How to build a table

```tsx
<div className="zr-table-wrap">
  <table className="zr-table min-w-[720px]">   {/* min-w keeps columns sensible on mobile */}
    <thead>
      <tr>
        <th>Name</th>
        <th className="zr-num">Total</th>   {/* right-aligned tabular numeric header */}
        <th>Status</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>
      {rows.map((r) => (
        <tr key={r.id}>
          <td className="font-medium">{r.name}</td>
          <td className="zr-num font-mono">{money(r.total_cents)}</td>
          <td><StatusBadge status={r.status} /></td>
          <td className="zr-cell-pad">
            <div className="flex flex-wrap items-center gap-2">
              <button className="zr-action zr-action--pri">Publish</button>
              <button className="zr-action">⧉ Duplicate</button>
            </div>
          </td>
        </tr>
      ))}
      {rows.length === 0 && (
        <tr><td colSpan={4} className="text-center text-[var(--zr-faint)] py-8">No rows yet.</td></tr>
      )}
    </tbody>
  </table>
</div>
```

The skin (in `src/index.css`) owns all of this so screens don't restyle it:

| Part | Spec |
|---|---|
| Container (`.zr-table-wrap`) | Surface, 1px `--zr-border`, 12px radius, `overflow:auto` (horizontal scroll on mobile) |
| Header row | 42px, 11px uppercase Plex Sans 600, `--zr-faint`, `--zr-bg` fill, bottom `--zr-header-border`, **sticky on scroll** |
| Body row | 52px, 13.5px Plex Sans 400, 1px `--zr-divider`, whole-row hover `--zr-row-hover` |
| Cell padding | `0 14px`; column dividers use `--zr-divider`. Add `.zr-cell-pad` to cells hosting inline controls / wrapped buttons |
| Numeric column | `.zr-num` on th/td — right-aligned + `tabular-nums`; pair with `font-mono` for prices/counts |

### Reusable primitives

| Class / component | Purpose |
|---|---|
| `.zr-chk` | 16×16 selection checkbox (`<input type="checkbox" className="zr-chk">`); accent fill + white ✓ when checked |
| `<StatusBadge status="…" />` / `.zr-pill .zr-pill--{live\|pending\|draft\|void}` | Status pill — 6px dot + label, semantic background |
| `.zr-action` / `.zr-action--pri` / `.zr-action--danger` | Row/toolbar buttons — ghost by default; **one** `--pri` (solid accent) per row max; `--danger` for destructive |
| `.zr-chip` + `.zr-chip__dot` | Inline category/tag chip — solid 1px border + small colour dot, used inside a cell |

### Do / Don't

- **Do** reuse `.zr-table` / `.zr-num` / `.zr-cell-pad` verbatim; only change the
  columns per screen.
- **Don't** invent a new row height, divider colour, or pill shape — extend this
  pattern instead of styling one-off.

---

## 4. Buttons & controls

- **Primary** (`.zr-action--pri`, solid `--zr-accent`) — one per view/row, the single
  most important commit action.
- **Ghost** (`.zr-action`) — row-level and toolbar secondary actions.
- Filter/utility chips live in the header bar; structural "+ Add…" creates rows/tabs.

Existing brand button classes (`bg-brand-600 hover:bg-brand-700 …`) remain valid for
form-level primary buttons; `.zr-action*` is for table/toolbar action affordances.
