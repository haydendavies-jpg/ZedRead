# ZedRead Portal — Frontend Rules

This file is the single source of truth for `pos-portal/` code style, brand, and component patterns.
Read it before writing any React, Tailwind, or TypeScript in this directory.

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

### Typography

- **Wordmark** — `Lora` serif, weight 700, loaded from Google Fonts via `src/index.css`.
  Apply with `style={{ fontFamily: "'Lora', serif", fontWeight: 700 }}`.
- **Tagline** — "POS You Can Count On" in `tracking-widest uppercase` at `0.6rem`.
- **Body** — `system-ui, 'Segoe UI', Roboto, sans-serif` (set globally on `body`).

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
- Every list page uses `{ params: { limit: 200 } }` for now (pagination added later).
- Every create/edit form lives in a `<Modal>`.
- Every write mutation has `onError` that sets a `formError` state string.
- Every list page has a `"No X yet."` empty state row.
- Every table with a parent entity shows the parent's `EntityIdChip` in its own column before the parent name column.

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
