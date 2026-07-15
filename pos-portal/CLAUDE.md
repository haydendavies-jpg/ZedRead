# ZedRead Portal — Frontend Rules

This file is the single source of truth for `pos-portal/` code style, brand, and component patterns.
Read it before writing any React, Tailwind, or TypeScript in this directory.

---

## Design Guide (colour + table standards) — READ FIRST for any UI work

`design_guide/PORTAL_DESIGN_GUIDE.md` is the authoritative colour-token and data-table
standard for **both** portals (admin + management), with the original high-fidelity
mockup saved next to it as `ZedRead_Portal_Design_Guide.html`. It is implemented in
`src/index.css` as `--zr-*` custom properties (light on `:root`, dark on `.dark`) plus a
global table skin.

**Every data table MUST use the shared skin** — do not hand-roll table styling:

```tsx
<div className="zr-table-wrap">
  <table className="zr-table min-w-[720px]">
    <thead><tr><th>Name</th><th className="zr-num">Total</th><th>Status</th></tr></thead>
    <tbody>
      <tr>
        <td className="font-medium">…</td>
        <td className="zr-num font-mono">…</td>
        <td><StatusBadge status={s} /></td>
      </tr>
    </tbody>
  </table>
</div>
```

- Header/row heights, dividers, hover, sticky header, cell padding are all owned by
  `.zr-table` — never re-style them per screen. Add `.zr-num` for numeric columns and
  `.zr-cell-pad` to cells hosting inline controls / wrapped action buttons.
- Status pills: use `<StatusBadge status="…" />` (maps every status onto the four
  semantic families) or `.zr-pill .zr-pill--{live|pending|draft|void}` directly.
- Row/toolbar buttons: `.zr-action`, `.zr-action--pri` (one primary per row), `.zr-action--danger`.
- Selection checkbox: `.zr-chk`. Inline category chip: `.zr-chip` + `.zr-chip__dot`.
- Chrome (background, sidebar, borders) reads `--zr-bg` / `--zr-sidebar` / `--zr-border`.
  When adding chrome, prefer these tokens over raw `gray-*` utilities.

---

## Brand

### Colors

The ZedRead brand color is a deep crimson. The full scale is defined in `src/index.css` via Tailwind's
`@theme` directive and is available as `brand-*` utility classes throughout the app.

| Token | Hex | Usage |
|---|---|---|
| `brand-50` | `#fdf2f4` | Active nav background |
| `brand-500` | `#c94060` | Focus rings (`focus:ring-brand-500`) |
| `brand-600` | `#a82040` | Primary buttons, action links |
| `brand-700` | `#8a1c35` | Hover state for buttons (`hover:bg-brand-700`) |
| `brand-800` | `#7b1d2a` | Wordmark, active nav text |

**Never use `indigo-*` classes.** All interactive elements use `brand-*`.

### Dark mode (Menu Studio redesign)

`ThemeContext` (`src/context/ThemeContext.tsx`) toggles a `dark` class on `<html>`, persisted to
`localStorage`, applied portal-wide. `src/index.css` registers `@custom-variant dark (&:where(.dark,
.dark *));` so Tailwind's `dark:` variant works. Toggle lives in `Layout.tsx`'s sidebar footer
(moon/sun icon). New/edited components must carry `dark:` companions for `bg-white`, `bg-gray-50`,
`border-gray-200/300`, `divide-gray-100/200`, and `text-gray-400/500/600/700/900` — see any Menu
Studio page for the established pairing (e.g. `bg-white dark:bg-gray-800`, `text-gray-900
dark:text-gray-100`). Older pages were swept mechanically to the same pairs; a perfect per-component
pass wasn't done everywhere — flag anything that reads wrong in dark mode rather than assuming it's
covered.

### Typography (Portal Design Guide §02)

The design guide's font system is now applied **portal-wide** (previously this was a flagged
conflict where only Menu Studio adopted it; that has been resolved in favour of the guide):

- **Interface / body** — `IBM Plex Sans` (400–700), set globally on `body` in `src/index.css`.
  Every control, label, and body of text inherits it. The `.zr-table` skin also sets it explicitly.
- **Titles** — `Source Serif 4` (600/700) via the Tailwind `font-serif` token, for page titles,
  card/section titles, and the sidebar **wordmark** (`font-serif font-bold` — see `Layout.tsx`,
  `MenuStudioPage.tsx`). `Lora` remains loaded and is still used on the standalone login page.
- **Numeric / tabular** — `IBM Plex Mono` via the `font-mono` token, for IDs, prices, time ranges;
  pair with `.zr-num` in tables.
- **Tagline** — "POS You Can Count On" in `tracking-widest uppercase` at `0.6rem`.

All three families are loaded via non-blocking `<link>` tags in `index.html`.

### Logo usage

The login page and sidebar both display the wordmark + tagline. Use this exact pattern:

```tsx
<span className="text-brand-800" style={{ fontFamily: "'Lora', serif", fontSize: '2rem', fontWeight: 700 }}>
  ZedRead
</span>
<p className="text-gray-400 tracking-widest uppercase" style={{ fontSize: '0.6rem' }}>
  POS You Can Count On
</p>
```

---

## Component patterns

### Buttons — primary action

```tsx
<button className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors">
  Label
</button>
```

Always add `disabled={mutation.isPending}` on submit buttons to prevent double-submission.

### Text inputs and selects

```tsx
className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
```

### Action links (Edit, inline table actions)

```tsx
<button className="text-brand-600 hover:underline text-xs">Edit</button>
```

### Modals

Use `src/components/Modal.tsx`. Pass `title` and `onClose`. Put the `<form>` inside the modal body,
not wrapping the modal itself.

---

## Page structure rules

- Routes are thin — fetch logic lives in `queryFn` functions defined at module scope.
- Every list page fetches the **complete** list via `fetchAll<T>(url, params)` from
  `src/api/axios.ts` (pages through `skip`/`limit` until a short page — never a single bounded
  `{ limit: N }` request, which silently drops rows past the cap). Exception: unbounded-growth
  lists (Invoices) use true server-side pagination — 50/page with Prev/Next controls, filters
  applied by the backend, and a `useEffect` snapping back to page 1 on any filter change.
- Every create/edit form lives in a `<Modal>`.
- Every write mutation has `onError` that sets a `formError` state string.
- Every list page has a `"No X yet."` empty state row.
- Every table with a parent entity shows the parent's `EntityIdChip` in its own column before the parent name column.

---

## Mutation error handling — invalidate on onError too (CRITICAL)

Write mutations must call `invalidateQueries` in **both** `onSuccess` and `onError`.

The backend can successfully write to the database but fail during response serialization
(e.g. a Pydantic type mismatch on the response model). When this happens the server returns
a 500, `onSuccess` never fires, and the list never re-fetches — so the user sees stale data
even though the record was created. This is the hardest class of bug to diagnose because
Supabase shows the row but the portal shows an error and an empty list.

```tsx
const createMutation = useMutation({
  mutationFn: (body) => api.post('/pos-users', body),
  onSuccess: () => {
    invalidateList()
    setShowCreate(false)
    resetForm()
  },
  onError: (e: any) => {
    invalidateList() // re-fetch so DB-written records appear even if response serialization failed
    setFormError(e?.response?.data?.detail ?? 'Failed to create user.')
  },
})
```

---

## Filter patterns

Every list page has client-side filters. All filtering happens against already-fetched data —
no extra API calls. Show a count chip `X of Y` and a "Clear filters" link.

```tsx
const filtered = items.filter((item) => {
  if (search && !item.name.toLowerCase().includes(search.toLowerCase())) return false
  if (statusFilter === 'active' && !item.is_active) return false
  if (statusFilter === 'inactive' && item.is_active) return false
  return true
})

const hasFilters = search || statusFilter

// In JSX:
{hasFilters && (
  <button
    onClick={() => { setSearch(''); setStatusFilter('') }}
    className="text-xs text-gray-400 hover:text-gray-600"
  >
    Clear filters
  </button>
)}
<span className="text-xs text-gray-400 ml-auto">{filtered.length} of {items.length}</span>
```

### Filter label placement — label ABOVE the control

Filter labels must always appear **above** the input or select, never inline beside it.
Use a `<div>` wrapper with `flex flex-col gap-1` and a `<label>` with `text-xs font-medium text-gray-500`.

```tsx
// ✅ Correct — label above
<div className="flex flex-col gap-1">
  <label className="text-xs font-medium text-gray-500">Status</label>
  <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
    className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-500">
    <option value="">Any</option>
    <option value="active">Active</option>
    <option value="inactive">Inactive</option>
  </select>
</div>

// ❌ Wrong — label inline beside control
<label className="flex items-center gap-1.5 text-xs text-gray-500 font-medium">
  Status
  <select ...>...</select>
</label>
```

The filter bar wraps these `<div>` columns in a `flex flex-wrap items-end gap-3` container
(`items-end` keeps controls bottom-aligned when labels cause different heights).

Filter controls use a slightly smaller padding than form inputs:

```tsx
className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
```

---

## Mobile / responsive design (REQUIRED on every page)

Every page must work on a 375px-wide screen. Apply these patterns consistently:

### Page wrapper
```tsx
<div className="p-4 sm:p-6">
```

### Page header row
```tsx
<div className="flex flex-wrap items-center justify-between gap-3 mb-4">
```
Use `flex-wrap` so the title and action button stack vertically on narrow screens.

### Filter bar
```tsx
<div className="flex flex-wrap items-center gap-2 mb-4">
```
Filters already use `flex-wrap` — keep it. On mobile each filter becomes full-width if needed.

### Table container — always wrap in overflow-x-auto
```tsx
<div className="overflow-x-auto rounded-xl border border-gray-200">
  <table className="w-full text-sm min-w-[600px]">
    ...
  </table>
</div>
```
`min-w-[600px]` (or appropriate value) keeps column widths sensible; the outer `overflow-x-auto` allows horizontal scroll on mobile rather than breaking the layout.

### Layout sidebar (mobile)
The sidebar collapses on mobile. A hamburger button (`☰`) in the top-left of the main area toggles it. When open, the sidebar overlays content (fixed position). Backdrop click closes it.

### Modal
`Modal.tsx` already uses `mx-4 max-w-md w-full` — this is correct. Do not remove `mx-4`.

---

## File locations

| What | Where |
|---|---|
| Pages | `src/pages/` |
| Shared components | `src/components/` |
| API client + interceptors | `src/api/axios.ts` |
| Auth context + JWT helpers | `src/context/AuthContext.tsx` |
| TypeScript types | `src/types.ts` |
| Global styles + Tailwind theme | `src/index.css` |
