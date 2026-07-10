# ZedRead — Stages 16–24 Execution Plan

Companion to `ROADMAP.md`/`STAGE_STATUS.md` (which track phase/stage status) and `ROLE_MODEL.md`
(the Stage 15 design doc this plan builds on). This document is the execution-level reference for
Stages 16–24 — each section is self-contained: open a fresh session, read `CLAUDE.md` +
`ARCHITECTURE_MAP.md` + this file's section for the stage you're building, and you have what you
need. Every section quotes the original request line(s) it satisfies.

Codebase facts this plan relies on (verified against the actual code, not assumptions):
- `products.ref` and `categories.ref` already exist as DB columns (migration `0013`, `PRD-000001`/
  `CAT-000001` sequence pattern) but were never wired into the SQLAlchemy model or Pydantic schema —
  dormant, unused today.
- `Product.description` and `Product.photo_url` are already fully built (model + schema + routes).
- Product photo upload currently caps at **500 KB** (`_MAX_PHOTO_BYTES` in `product_service.py`,
  documented in `models/product.py` line 90) with **no dimension validation at all** — no check for
  the 500×500 minimum the user specified, and no 1:1 ratio guidance surfaced anywhere.
- `audit_logs` (`app/models/audit_log.py`) already stores `before_state`/`after_state` as JSONB per
  row, and `invoice_service.py` already calls `log_action(entity_type='invoice', ...)` on every
  mutation (pay, void, refund, discount) — an invoice change log is a filtered query, not a new table.
- `access_profile_page_permissions` + `app/constants/pages.py` (17-page catalog) are fully built
  server-side (Stage 15) but zero portal UI calls those endpoints today.
- No existing PDF generation anywhere in the backend to match a style against.

---

## Stage 16 — Reporting Groups

**Original ask:**
> "I want to add reporting groups, reporting groups a stage higher then Categories, you add
> categories to a reporting group, there is a default group that new categories go in by default,
> you can create multiple reporting groups however each category can only have one reporting group
> and is prompted to be added to a group on creation, each category must have a reporting group."
>
> "Add reporting groups to the side menu in the management portal."

**Resolved decision:** brand-scoped (matches Categories' current scope, per user confirmation).

**Build plan:**
- Migration: new `reporting_groups` table — `id`, `brand_id` (FK), `name`, `is_default` (bool),
  `is_system` (bool), `ref` (new `RPG-000001` sequence, same mechanism as migration `0013`:
  `nextval()` server default), `created_at`/`updated_at`.
- Seed: on brand creation (and once via data migration for existing brands), auto-create one
  `is_system=True, is_default=True` reporting group, undeletable — same pattern as Category's
  existing system "Uncategorised" seed (Stage 8).
- `categories.reporting_group_id` — **NOT NULL** FK. Migration backfills every existing category to
  its brand's default group before adding the constraint.
- Service layer (`category_service.py`): create/update requires `reporting_group_id`; if omitted on
  create, auto-assign the brand's default (matches "prompted... by default" — the portal prompts,
  the API guarantees it's never actually null).
- Delete guard: deleting a non-default reporting group with categories still attached is blocked
  (reassign first) — mirrors the existing "can't delete category with products" rule.
- New `reporting_group_service.py` + `routes/reporting_groups.py`: CRUD, paginated list, audit logged
  per CLAUDE.md rule 7.
- Portal: new sidebar entry "Reporting Groups" (Product & Menus section), CRUD table page structured
  like `CategoriesPage.tsx`; `CategoriesPage.tsx`'s create/edit modal gets a required Reporting Group
  select.
- Permission catalog: add `reporting_groups` page key to `app/constants/pages.py` and to
  `ROLE_MODEL.md` §6's table (Product & Menus category), pick default role grants + license tier
  alongside `categories`.

**Depends on:** nothing (can start immediately after Stage 15 wraps).

---

## Stage 17 — Delegated User Creation

**Original ask:**
> "Allow users to add POS users lower then their access level in the management portal, this can be
> done at site/brand/group but can only be done from that level down eg Site can only add at that
> site, brand can add at the brand level and assign sites downward, a user cannot grant a level of
> access higher then themself."

**Build plan:**
- Scope ladder enforced server-side: a grantor's highest backend-access scope determines the ceiling
  — Site-scoped grantor creates/grants at that Site only; Brand-scoped grantor creates/grants at that
  Brand or any Site beneath it; Group-scoped grantor creates/grants at Group, its Brands, or their
  Sites.
- Role ceiling: grantor cannot assign a role ranked above their own highest grant. Master User is
  excluded from delegated creation entirely (immutable, tied to the site itself per `ROLE_MODEL.md`
  §2) — no one delegates into it.
- Implementation point: the scope-and-rank check belongs wherever `UserAccessGrant` rows are created
  today — `access_grant_service.py` (create/invite paths). Add a `assert_can_grant(grantor, target_scope,
  target_role)` guard called before insert; reject with 403.
- Audit: successful delegated creation logs actor, granted scope, and granted role in the same
  transaction (rule 7). Rejected attempts don't need their own audit row (not a state change) but
  should still structlog at WARN for traceability.
- Portal: the existing Users create form's scope-picker and role-picker get filtered down to what the
  logged-in user is actually allowed to grant (client-side UX only — the 403 guard above is the real
  enforcement).

**Depends on:** nothing new — extends the existing `user_access_grants` model from Stage 7.

---

## Stage 18 — Permission Scopes Portal UI

**Original ask:**
> "The permission scopes that were mentioned in earlier builds need to be added to the management
> portal & the MD needs to be updated to add any new pages from the menu to the permissions."

**Build plan:**
- Already built server-side (Stage 15, unused by the frontend): `GET/POST
  /access-profiles/{id}/pages`, `DELETE /access-profiles/{id}/pages/{page_key}`, `GET
  /access-profiles/{id}/visible-pages?site_id=`.
- New portal page (or a tab on an existing Access Profiles / Users page): list access profiles per
  scope, toggle each page-level grant. License-gated pages render **disabled with a visible reason**
  (e.g. "Requires Pro plan"), not silently hidden — so an admin understands why a toggle is greyed
  out rather than assuming a bug.
- "MD needs to be updated to add any new pages" — this becomes a **standing rule**, not a one-time
  task: every stage from here on that ships a new portal page (Reporting Groups in Stage 16,
  Modifiers in Stage 22, Invoices already has a key) must add its `page_key` to
  `app/constants/pages.py` and to `ROLE_MODEL.md` §6's table in the *same commit* that ships the page.
  Call this out explicitly in each future stage's PR description as a checklist item. (Variants do
  **not** get a page key — see Stage 22 below, redrafted to nest them inline on the Products page.)

**Depends on:** Stage 15 (already built). Should land before or alongside Stage 16 so the
`reporting_groups` page key has somewhere to be managed from.

---

## Stage 19 — Bulk Import/Export (XLSX)

**Original ask:**
> "Products Categories & Reporting groups need a bulk upload option, you can export a template to a
> XLSX file (or any other file type you recommend), this will be importable and exportable from the
> relevant pages."
>
> "Products table needs to display the product code, all imports and exports for table data base on
> the code/ID and overwrite based on headers."

**Resolved decision:** XLSX via `openpyxl`, not CSV — needed for a frozen header row, data-validation
dropdowns (category/reporting-group columns pick from existing names instead of free text), and
round-tripping cleanly through Excel for bulk edits. CSV can't do any of that.

**Build plan:**
- Prerequisite: wire `products.ref` and `categories.ref` (dormant migration-`0013` columns) into
  their ORM models and Pydantic schemas — this is what "product code" (and category code) means, and
  it's the import/export matching key. (This can land as the first slice of Stage 19, or be pulled
  into Stage 24 instead — same underlying change either way; doing it here means Stage 19 isn't
  blocked waiting on Stage 24.)
- Shared `export_service.py` / `import_service.py`, built once, reused for Products, Categories,
  Reporting Groups now and Variants/Modifiers in Stage 22:
  - **Template export**: header row + one example row + Excel data-validation dropdowns for any
    foreign-key-ish column (category name, reporting group name).
  - **Full export**: current table's data, respecting whatever filters are active on the page (ties
    into Stage 20's filter bars).
  - **Import**: validate-then-upsert. Row matched to an existing record by its `ref` code if present;
    absent `ref` → treated as a new record, assigned the next code from the sequence. **"Overwrite
    based on headers"** = only columns actually present in the uploaded sheet's header row are
    written; columns from the schema that aren't in the header are left untouched (partial-update
    semantics) — this reading was confirmed with the user.
  - Every changed row still gets its own `audit_logs` entry (rule 7/11); all rows from one upload
    share a batch `import_id` so a whole import can be traced/reasoned about together.
- Routes: `GET /products/export/template`, `GET /products/export`, `POST /products/import` (and the
  equivalent for categories, reporting groups) — thin, logic in the shared services.

**Depends on:** Stage 16 (reporting groups must exist before they're an export/import column) and
benefits from Stage 20's filters (full export uses active filters), but the import/export engine
itself has no hard dependency and could be built in parallel.

---

## Stage 20 — Table UX (columns, inline edit, filters)

**Original ask:**
> "Reporting group and categories need to be displayed in the product table in the products page in
> the management portal."
>
> "Products, categories & Reporting groups need to be editable in the table on their relevant pages
> in the management portal."
>
> "Products, categories & reporting groups need filters on their pages."

**Build plan:**
- Products table (`ProductsPage.tsx`) gains **Reporting Group** and **Category** columns. Reporting
  Group is derived via the Category → Reporting Group FK chain at query time (join), not
  denormalized onto Product — avoids a sync-drift bug if a category's group changes later.
- Inline cell edit added to Products/Categories/Reporting-Groups tables (name, price, category,
  reporting group, active-state) as click-to-edit, alongside — not replacing — the existing
  modal-based create flow.
- Shared filter-bar component: category, reporting group, active/inactive, free-text search on
  name/code. Same component reused across all three pages. Must `flex-wrap` at 375px per CLAUDE.md
  rule 16 (test at that width before calling the stage done).

**Depends on:** Stage 16 (Reporting Groups must exist to filter/display by).

---

## Stage 21 — Invoice Reporting

**Original ask:**
> "Invoice need to be reportable, openable in a detailed view, exportable in a standard PDF style,
> exportable as a XLSX file of the whole table based on filters in the management portal, the
> invoice must have a log agaisnt any changes made to it after creation like refunds, updates etc in
> the detailed view."

**Resolved decision (change log):** reuse `audit_logs` filtered by `entity_type='invoice',
entity_id=<id>` — confirmed `invoice_service.py` already writes a row on every post-creation mutation
(pay, void, refund, discount) with full before/after JSONB. A dedicated `invoice_change_log` table
would just duplicate that data. The detail view's change-log panel is a read-only query, not new
write-path work.

**Resolved decision (PDF):** no existing style to match, no user preference given — recommend
`weasyprint` (HTML/CSS-authored layout, easiest to iterate on and restyle later) over `reportlab`
(more programmatic, more code for the same visual result). Standard single-invoice receipt/invoice
layout.

**Build plan:**
- List page (page key `invoices` already exists in the catalog): filters — date range, site, payment
  status, amount range — plus **XLSX export of the filtered set** via Stage 19's shared export
  service.
- Detail view: full invoice (line items, modifiers, tax breakdown, payments) plus the change-log
  panel described above (actor, timestamp, before/after diff, rendered from the JSONB).
- PDF export endpoint: renders an HTML template with `weasyprint`, single invoice, standard layout.

**Depends on:** Stage 19 (export service).

---

## Stage 22 — Modifiers Portal Page + Inline Product Variants (redrafted)

**Original ask:**
> "Variant, Modifiers and Combos need to be added to the Management portal menu and have filters
> edits exports & imports etc, provide me with the current designed scope so it can be reviewed, All
> of these need their own relevent ID for the user that is relateable as a human in scope similar to
> product ID. Variants and combos need a display name that is different from the name used in
> backend to make management distinguishable and easy to read."
>
> "Variants link to products and need to be able to reference that link in both the product and the
> Variant."

**Original resolved decisions (superseded — kept for history):** one combined Variants+Combos page
with Modifiers excluded (inline on the Product page). Reopened and reversed in review — see below.

**Revised decisions:**
- **Combos dropped from the portal plan entirely.** Combos become part of the Modifiers design
  instead, to be scoped in a later pass. Nothing changes in the backend for now:
  `product_combo_groups`/`product_combo_options`, `combos.py`, `combo_service.py` all stay as built
  in Stage 9. No `ref`, no `display_name`, no portal page for Combos in this stage. The `combos` page
  key is retired from the catalog (`ROLE_MODEL.md` §6).
- **Variants get no standalone portal page.** They render as nested rows directly under their parent
  product in the Products table — indented, `↳`-style connector (per the reviewed mock), same table,
  same filters, same inline-edit pattern the product rows already use (Stage 20). No new page key;
  visibility is governed by the existing `products` grant. They keep `ref` (`VAR-000001`) and
  `display_name`, since both are still useful — `ref` for import/export row-matching, `display_name`
  for the nested-row label shown in place of the internal `name`.
- **Modifiers get their own dedicated portal page** — the treatment originally reserved for
  Variants/Combos flips onto Modifiers instead. New page key `modifiers` (replacing the old
  `variants_modifiers` placeholder). `ref` (`MOD-000001`) and `display_name` apply to `ModifierGroup`
  (the page-level entity, same level as Product) — not to `ModifierOption`, which stays a plain
  name + price_delta_cents sub-row, mirroring how Variant attribute values aren't independently
  ref'd either.
- Modifiers are **configured on their own page, then attached to products** — not edited inline on
  the Product page as originally planned. The existing `product_modifier_group_links` M:N join
  already models this; the new work is a picker UI on the product side (product edit form or a new
  Product detail surface) to link/unlink `ModifierGroup`s, plus the Modifiers page itself.

**Build plan:**
- New `ref` sequence: `VAR-000001` (Variant) — unchanged from the original plan, same
  migration-`0013` mechanism. New `display_name` column on `Variant` (nullable).
- Products table (`ProductsPage.tsx`): expand each product row into its variant rows inline —
  indented name, `ref`/`display_name`, price override (falls back to product price when NULL),
  active-state, inline-editable like the existing product cells. No separate sidebar entry.
- New `ref` sequence: `MOD-000001` (ModifierGroup), same mechanism. New `display_name` column on
  `ModifierGroup` (nullable).
- New Modifiers portal page (sidebar entry, `page_key` = `modifiers`): table of `ModifierGroup`s with
  `ref` + `display_name` columns, filters (active state, text search), inline edit (name,
  display_name, min/max selections, active), import/export via Stage 19's framework. `ModifierOption`
  rows nest under their group the same way Variants nest under Products, for visual consistency.
- Attach-to-product picker: on the product side, a multi-select against existing `ModifierGroup`s
  that writes/removes rows in `product_modifier_group_links` — no new schema.
- Cross-linking: `Variant.product_id` already exists — surface it as the nested-row relationship
  described above; no separate "linked product" detail view needed since Variants have no standalone
  page to show it on.
- `app/constants/pages.py`: retire `variants_modifiers` and `combos`, add `modifiers`.
  `app/constants/license_plans.py`: `PRO_PLAN_PAGES` updated to reference `modifiers` instead of the
  two retired keys. Both done ahead of the rest of the build (low-risk placeholder correction).

**Deferred:** Combos redesign (folded into Modifiers) — not scoped yet, comes back as its own future
stage once the user defines it.

**Depends on:** Stage 19 (import/export framework).

---

## Stage 23 — POS Menu Builder

**Original ask:**
> "A POS menu prototype that can be generated and published to the POS app, this is a graphical
> layout that is used in the android application, you can add tabs to the menu to put product
> buttons inside, these are purely graphical and relate back to the product based on product code.
> based on scope you can have more then one selectable."

**Build plan:**
- New tables: `menu_layouts` (id, scope [brand/site], name, `is_published`, version),
  `menu_tabs` (layout_id, ordered), `menu_buttons` (tab_id, product **`ref` code** — deliberately not
  a product FK, so a button keeps working if the underlying product is deleted and recreated with the
  same code, per the "purely graphical... relate back... based on product code" wording).
- Portal builder UI: drag/drop tabs and buttons in a grid, live name/price preview pulled from the
  catalog by resolving the code at edit time.
- Publish-time validation: warn (don't silently fail) if a button's code no longer resolves to an
  active product.
- "More than one selectable" = more than one `menu_layout` can be `is_published=True`
  simultaneously — e.g. different layouts per site, or day-part menus (breakfast/lunch) live at once.
- `GET /pos/menu-layout?site_id=` is the publish contract Android will eventually consume — build the
  contract now, no Android-side work required in this stage.
- Explicit prototype scope: single-level tabs + buttons only, **no nested sub-menus**.

**Depends on:** Stage 24 conceptually (buttons reference `products.ref`, which Stage 19/24 surfaces)
but not blocked by it since `ref` already exists in the DB — only needs the ORM/schema wiring done.

---

## Stage 24 — Product Model Extensions

**Original ask:**
> "Products table needs to display the product code, all imports and exports for table data base on
> the code/ID and overwrite based on headers." *(code-surfacing — may land in Stage 19 instead, see
> above; listed here too since it's fundamentally a Product model change)*
>
> "Products need a Description field" — **already exists** (`Product.description`, fully wired
> model → schema → routes). No work item.
>
> "products need a photo field (1mb Limit 500x500 minimum Recommended 1:1 ratio)" — **partially
> exists**: `Product.photo_url` + upload endpoint are built, but the current cap is **500 KB, not
> 1 MB** as specified, and there is **no dimension validation at all** (no check for the 500×500
> minimum). Build plan: raise `_MAX_PHOTO_BYTES` to 1 MB in `product_service.py`, add a
> dimension check (reject uploads below 500×500; surface a 1:1-ratio recommendation in the portal's
> upload UI as guidance, not a hard rejection since the user said "recommended" not "required").
>
> "Products need a print name, that is an alternative for production dockets." — new nullable
> `print_name` column, falls back to `name` when unset. Production docket printing itself stays out
> of scope (Android printing work, not yet scheduled).
>
> "an optional product is an open item, this item can have A flexable price and name at time of
> selection but will default to the fields set in the products details, this item needs to have a
> permission tied to user permission and ability to set limits on price." — new `is_open_item` flag
> on Product. At sale time (Android, out of scope here beyond the data model), price/name are
> freely enterable, defaulting to the product's own `base_price_cents`/`name`. New
> `can_use_open_item` capability flag on `AccessProfile` (a capability, not a page grant — it's an
> action permission, doesn't fit the page-permission system) plus an optional
> `open_item_max_price_cents` ceiling.

**Depends on:** none blocking — can run in parallel with most other stages. If Stage 19 already
surfaced `products.ref`, this stage's first bullet is already done by the time it starts.

---

## How this relates to `ROADMAP.md` / `STAGE_STATUS.md`

Those two stay as the scannable phase/stage overview and checklist. This file is where the
execution-level detail lives — see the "full detail" pointer added to each of Phases 5–9 in
`ROADMAP.md`.
