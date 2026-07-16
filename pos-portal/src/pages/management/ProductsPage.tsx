/** Catalog products management page — list, create, edit, archive products.
 *
 * Stage 20: table shows a joined Category column, supports inline cell edit
 * (name, category, price, status) and a shared filter bar (Category,
 * Reporting Group, Status — Reporting Group is a filter only, not a column:
 * it's derived from Category, not a Product field).
 *
 * Post-Stage-23: the Modifiers cell opens ModifierPickerModal (attach/
 * reorder/detach a product's modifier sets); a checkbox column supports
 * multi-select with a floating bulk-action bar (category, price, % markup,
 * tax, modifier attach, archive) backed by POST /products/bulk. There is no
 * hard-delete anywhere in this app — "archive" (soft-delete via is_active)
 * is the only removal action, both per-row (StatusBadge) and in bulk.
 */

import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, fetchAll } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { Modal } from '../../components/Modal'
import { StatusBadge } from '../../components/StatusBadge'
import { EntityIdChip } from '../../components/EntityIdChip'
import { EditableText, EditableSelect } from '../../components/EditableCell'
import { FilterBar, type FilterConfig } from '../../components/FilterBar'
import { ModifierPickerModal } from '../../components/ModifierPickerModal'
import { apiErrorMessage } from '../../utils/apiError'
import type { Product, ProductListItem, Category, ReportingGroup, TaxCategory, ModifierGroup } from '../../types'

function centsToDisplay(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

export function ProductsPage() {
  const qc = useQueryClient()
  const brandId = useMgmtBrandId()
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<ProductListItem | null>(null)

  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [reportingGroupFilter, setReportingGroupFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const params = brandId ? { brand_id: brandId } : {}

  const { data: products = [], isLoading } = useQuery<ProductListItem[]>({
    queryKey: ['products', brandId],
    queryFn: () => fetchAll<ProductListItem>('/products', { ...params, include_inactive: true }),
    enabled: brandId !== undefined,
  })

  const { data: categories = [] } = useQuery<Category[]>({
    queryKey: ['categories', brandId],
    queryFn: () => fetchAll<Category>('/categories', params),
    enabled: !!brandId,
  })

  const { data: reportingGroups = [] } = useQuery<ReportingGroup[]>({
    queryKey: ['reporting-groups', brandId],
    queryFn: () => fetchAll<ReportingGroup>('/reporting-groups', params),
    enabled: !!brandId,
  })

  const { data: taxCategories = [] } = useQuery<TaxCategory[]>({
    queryKey: ['tax-categories', brandId],
    queryFn: () => fetchAll<TaxCategory>('/tax/categories', params),
    enabled: !!brandId,
  })

  const { data: modifierGroups = [] } = useQuery<ModifierGroup[]>({
    queryKey: ['modifier-groups', brandId],
    queryFn: () => fetchAll<ModifierGroup>('/modifier-groups', params),
    enabled: !!brandId,
  })

  const invalidateList = () => qc.invalidateQueries({ queryKey: ['products', brandId] })

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.patch(`/products/${id}`, body, { params }),
    onSuccess: invalidateList,
    onError: invalidateList,
  })

  const deactivate = useMutation({
    mutationFn: (id: string) => api.delete(`/products/${id}`, { params }),
    onSuccess: invalidateList,
    onError: invalidateList,
  })

  const activate = useMutation({
    mutationFn: (id: string) => api.post(`/products/${id}/activate`, {}, { params }),
    onSuccess: invalidateList,
    onError: invalidateList,
  })

  const [modifierPickerFor, setModifierPickerFor] = useState<ProductListItem | null>(null)

  // ── Row selection + bulk actions ──────────────────────────────────────────
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkError, setBulkError] = useState<string | null>(null)
  const [bulkSuccess, setBulkSuccess] = useState<string | null>(null)
  const [bulkPriceStr, setBulkPriceStr] = useState('')
  const [bulkMarkupStr, setBulkMarkupStr] = useState('')
  const selectAllRef = useRef<HTMLInputElement>(null)

  const toggleOne = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  const clearSelection = () => setSelected(new Set())

  const bulkOnSuccess = (msg: string) => () => {
    invalidateList()
    setBulkError(null)
    setBulkSuccess(msg)
    clearSelection()
  }
  const bulkOnError = (e: unknown) => {
    invalidateList()
    setBulkSuccess(null)
    setBulkError(apiErrorMessage(e, 'Bulk action failed.'))
  }

  const bulkUpdate = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post('/products/bulk', { product_ids: [...selected], ...body }, { params }),
  })

  const applyBulkCategory = (categoryId: string) => {
    if (!categoryId || selected.size === 0) return
    bulkUpdate.mutate(
      { category_id: categoryId },
      { onSuccess: bulkOnSuccess(`Updated category for ${selected.size} product(s).`), onError: bulkOnError },
    )
  }

  const applyBulkPrice = () => {
    const cents = Math.round(parseFloat(bulkPriceStr) * 100)
    if (isNaN(cents) || cents < 0 || selected.size === 0) return
    bulkUpdate.mutate(
      { price_cents: cents },
      {
        onSuccess: () => { bulkOnSuccess(`Updated price for ${selected.size} product(s).`)(); setBulkPriceStr('') },
        onError: bulkOnError,
      },
    )
  }

  const applyBulkMarkup = () => {
    const percent = parseFloat(bulkMarkupStr)
    if (isNaN(percent) || selected.size === 0) return
    bulkUpdate.mutate(
      { price_markup_percent: percent },
      {
        onSuccess: () => { bulkOnSuccess(`Applied ${percent}% markup to ${selected.size} product(s).`)(); setBulkMarkupStr('') },
        onError: bulkOnError,
      },
    )
  }

  const applyBulkTax = (taxCategoryId: string) => {
    if (!taxCategoryId || selected.size === 0) return
    bulkUpdate.mutate(
      { tax_category_id: taxCategoryId },
      { onSuccess: bulkOnSuccess(`Updated tax category for ${selected.size} product(s).`), onError: bulkOnError },
    )
  }

  const applyBulkModifier = (modifierGroupId: string) => {
    if (!modifierGroupId || selected.size === 0) return
    bulkUpdate.mutate(
      { modifier_group_id: modifierGroupId },
      { onSuccess: bulkOnSuccess(`Attached modifier set to ${selected.size} product(s).`), onError: bulkOnError },
    )
  }

  const applyBulkArchive = () => {
    if (selected.size === 0) return
    if (!confirm(`Archive ${selected.size} product(s)? They can be reactivated later.`)) return
    bulkUpdate.mutate(
      { is_active: false },
      { onSuccess: bulkOnSuccess(`Archived ${selected.size} product(s).`), onError: bulkOnError },
    )
  }

  const categoryOptions = categories.map((c) => ({ value: c.id, label: c.name }))

  const filtered = products.filter((p) => {
    if (search && !p.name.toLowerCase().includes(search.toLowerCase()) && !p.ref.toLowerCase().includes(search.toLowerCase())) return false
    if (categoryFilter && p.category_id !== categoryFilter) return false
    if (reportingGroupFilter && p.reporting_group_id !== reportingGroupFilter) return false
    if (statusFilter === 'active' && !p.is_active) return false
    if (statusFilter === 'inactive' && p.is_active) return false
    return true
  })

  const hasFilters = !!(search || categoryFilter || reportingGroupFilter || statusFilter)
  const clearFilters = () => { setSearch(''); setCategoryFilter(''); setReportingGroupFilter(''); setStatusFilter('') }

  // Selection is scoped to the currently-filtered/visible rows.
  const filteredIds = filtered.map((p) => p.id)
  const allSelected = filteredIds.length > 0 && filteredIds.every((id) => selected.has(id))
  const someSelected = filteredIds.some((id) => selected.has(id))
  if (selectAllRef.current) selectAllRef.current.indeterminate = someSelected && !allSelected
  const toggleAll = () => {
    setSelected((prev) => {
      if (filteredIds.every((id) => prev.has(id))) {
        const next = new Set(prev)
        filteredIds.forEach((id) => next.delete(id))
        return next
      }
      return new Set([...prev, ...filteredIds])
    })
  }

  const filters: FilterConfig[] = [
    {
      label: 'Category',
      value: categoryFilter,
      onChange: setCategoryFilter,
      options: [{ value: '', label: 'All categories' }, ...categoryOptions],
    },
    {
      label: 'Reporting Group',
      value: reportingGroupFilter,
      onChange: setReportingGroupFilter,
      options: [{ value: '', label: 'All reporting groups' }, ...reportingGroups.map((g) => ({ value: g.id, label: g.name }))],
    },
    {
      label: 'Status',
      value: statusFilter,
      onChange: setStatusFilter,
      options: [
        { value: '', label: 'All statuses' },
        { value: 'active', label: 'Active' },
        { value: 'inactive', label: 'Inactive' },
      ],
    },
  ]

  if (!brandId) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-gray-400">
        No brand context available. Use a brand-scope management token or select a brand.
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Products</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="px-3 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
        >
          Add product
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : (
        <>
          <FilterBar
            search={search}
            onSearchChange={setSearch}
            searchPlaceholder="Search by name or code…"
            filters={filters}
            hasFilters={hasFilters}
            onClear={clearFilters}
            resultCount={filtered.length}
            totalCount={products.length}
          />

          {/* ── Bulk action bar (shown when rows are selected) ──────────────── */}
          {selected.size > 0 && (
            <div className="flex flex-wrap items-center gap-3 mb-3 px-3 py-2 rounded-lg border border-brand-200 dark:border-brand-900 bg-brand-50 dark:bg-brand-950/30">
              <span className="text-sm font-medium text-brand-800 dark:text-brand-300">{selected.size} selected</span>

              <label className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
                Category
                <select
                  value=""
                  disabled={bulkUpdate.isPending}
                  onChange={(e) => { applyBulkCategory(e.target.value); e.target.value = '' }}
                  className="px-2 py-1 border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 rounded text-xs focus:outline-none focus:ring-1 focus:ring-brand-500"
                >
                  <option value="">Choose…</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </label>

              <div className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
                Price ($)
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={bulkPriceStr}
                  disabled={bulkUpdate.isPending}
                  onChange={(e) => setBulkPriceStr(e.target.value)}
                  className="w-20 px-2 py-1 border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 rounded text-xs focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
                <button
                  onClick={applyBulkPrice}
                  disabled={bulkUpdate.isPending || !bulkPriceStr}
                  className="text-brand-600 hover:text-brand-800 disabled:opacity-50 font-medium"
                >
                  Apply
                </button>
              </div>

              <div className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
                % markup
                <input
                  type="number"
                  step="1"
                  value={bulkMarkupStr}
                  disabled={bulkUpdate.isPending}
                  placeholder="+10"
                  onChange={(e) => setBulkMarkupStr(e.target.value)}
                  className="w-16 px-2 py-1 border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 rounded text-xs focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
                <button
                  onClick={applyBulkMarkup}
                  disabled={bulkUpdate.isPending || !bulkMarkupStr}
                  className="text-brand-600 hover:text-brand-800 disabled:opacity-50 font-medium"
                >
                  Apply
                </button>
              </div>

              <label className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
                Tax
                <select
                  value=""
                  disabled={bulkUpdate.isPending}
                  onChange={(e) => { applyBulkTax(e.target.value); e.target.value = '' }}
                  className="px-2 py-1 border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 rounded text-xs focus:outline-none focus:ring-1 focus:ring-brand-500"
                >
                  <option value="">Choose…</option>
                  {taxCategories.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              </label>

              <label className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
                Modifiers
                <select
                  value=""
                  disabled={bulkUpdate.isPending}
                  onChange={(e) => { applyBulkModifier(e.target.value); e.target.value = '' }}
                  className="px-2 py-1 border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 rounded text-xs focus:outline-none focus:ring-1 focus:ring-brand-500"
                >
                  <option value="">Choose…</option>
                  {modifierGroups.map((m) => (
                    <option key={m.id} value={m.id}>{m.name}</option>
                  ))}
                </select>
              </label>

              <button
                onClick={applyBulkArchive}
                disabled={bulkUpdate.isPending}
                className="text-xs font-medium text-red-600 hover:text-red-700 disabled:opacity-50"
              >
                Archive
              </button>
              <button
                onClick={clearSelection}
                disabled={bulkUpdate.isPending}
                className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 ml-auto"
              >
                Clear selection
              </button>
            </div>
          )}

          {bulkError && <p className="text-xs text-red-500 mb-3">{bulkError}</p>}
          {bulkSuccess && !bulkError && <p className="text-xs text-green-600 dark:text-green-400 mb-3">{bulkSuccess}</p>}

          <div className="zr-table-wrap">
            <table className="zr-table min-w-[1000px]">
              <thead>
                <tr>
                  <th className="w-10 px-4 py-3">
                    <input
                      ref={selectAllRef}
                      type="checkbox"
                      className="zr-chk"
                      checked={allSelected}
                      onChange={toggleAll}
                      aria-label="Select all"
                    />
                  </th>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Category</th>
                  <th>Price (inc.)</th>
                  <th>Price (ex.)</th>
                  <th>Tax</th>
                  <th>Modifiers</th>
                  <th>Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((p) => (
                  <tr key={p.id}>
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        className="zr-chk"
                        checked={selected.has(p.id)}
                        onChange={() => toggleOne(p.id)}
                        aria-label={`Select ${p.name}`}
                      />
                    </td>
                    <td className="px-4 py-3"><EntityIdChip id={p.id} ref={p.ref} /></td>
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">
                      <EditableText
                        value={p.name}
                        onSave={async (v) => { await patch.mutateAsync({ id: p.id, body: { name: v } }) }}
                      />
                    </td>
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: p.category_color }} />
                        <EditableSelect
                          value={p.category_id}
                          options={categoryOptions}
                          onSave={async (v) => { await patch.mutateAsync({ id: p.id, body: { category_id: v } }) }}
                        />
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300">
                      <EditableText
                        value={(p.base_price_cents / 100).toFixed(2)}
                        type="number"
                        formatDisplay={() => centsToDisplay(p.base_price_cents)}
                        onSave={async (v) => {
                          const cents = Math.round(parseFloat(v) * 100)
                          if (isNaN(cents) || cents < 0) throw new Error('Price must be a valid positive number.')
                          await patch.mutateAsync({ id: p.id, body: { base_price_cents: cents } })
                        }}
                      />
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{centsToDisplay(p.price_ex_cents)}</td>
                    <td className="px-4 py-3">
                      {p.is_taxable ? (
                        <span className="text-xs text-gray-700 dark:text-gray-300">Taxed</span>
                      ) : (
                        <span className="text-xs text-emerald-700 dark:text-emerald-400">Tax free</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => setModifierPickerFor(p)}
                        title="Manage modifier sets"
                        className="text-left"
                      >
                        {p.modifier_names ? (
                          <span className="inline-block max-w-[160px] truncate border border-brand-300 dark:border-brand-700 rounded-md px-2 py-1 text-xs text-gray-700 dark:text-gray-300 hover:bg-brand-50 dark:hover:bg-brand-950/30" title={p.modifier_names}>
                            {p.modifier_names}
                          </span>
                        ) : (
                          <span className="inline-block border border-dashed border-gray-300 dark:border-gray-600 rounded-md px-2 py-1 text-xs text-gray-400 dark:text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-700/50">None</span>
                        )}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge
                        status={p.is_active ? 'active' : 'archived'}
                        title={p.is_active ? 'Click to archive' : 'Click to reactivate'}
                        onClick={() => (p.is_active ? deactivate.mutate(p.id) : activate.mutate(p.id))}
                      />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => setEditing(p)}
                        className="text-brand-600 hover:text-brand-800 text-xs font-medium"
                      >
                        Edit
                      </button>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={11} className="px-4 py-8 text-center text-gray-400">
                      {products.length === 0 ? 'No products yet.' : 'No products match the current filters.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {(showCreate || editing) && (
        <ProductFormModal
          product={editing}
          brandId={brandId}
          categories={categories}
          onClose={() => { setShowCreate(false); setEditing(null) }}
          onSaved={() => {
            invalidateList()
            setShowCreate(false)
            setEditing(null)
          }}
        />
      )}

      {modifierPickerFor && (
        <ModifierPickerModal
          productId={modifierPickerFor.id}
          productName={modifierPickerFor.name}
          onClose={() => setModifierPickerFor(null)}
          onSaved={invalidateList}
        />
      )}
    </div>
  )
}

// ── Product form modal ─────────────────────────────────────────────────────────

interface ProductFormProps {
  product: Product | null
  brandId: string
  categories: Category[]
  onClose: () => void
  onSaved: () => void
}

/** The price actually charged at sale under a given taxability: inclusive when taxed, exclusive when not. */
function effectivePriceCents(product: Product, taxable: boolean): number {
  return taxable ? product.base_price_cents : product.price_ex_cents
}

function ProductFormModal({ product, brandId, categories, onClose, onSaved }: ProductFormProps) {
  const [name, setName] = useState(product?.name ?? '')
  const [description, setDescription] = useState(product?.description ?? '')
  // Taxability is a plain product flag. When taxed, the field holds the
  // tax-inclusive price and the exclusive price is derived server-side from
  // the brand's country rate. When tax free there is no tax to derive — the
  // field holds the exact price charged, so it shows/edits price_ex_cents.
  const [taxable, setTaxable] = useState(product ? product.is_taxable : true)
  const [priceStr, setPriceStr] = useState(
    product ? (effectivePriceCents(product, product.is_taxable) / 100).toFixed(2) : ''
  )
  const [categoryId, setCategoryId] = useState(product?.category_id ?? categories[0]?.id ?? '')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  /** Switch the Tax setting, updating the displayed price to what's actually charged under it. */
  const handleTaxableChange = (nextTaxable: boolean) => {
    setTaxable(nextTaxable)
    if (product) {
      setPriceStr((effectivePriceCents(product, nextTaxable) / 100).toFixed(2))
    }
  }

  const handleSave = async () => {
    const priceCents = Math.round(parseFloat(priceStr) * 100)
    if (isNaN(priceCents) || priceCents < 0) {
      setError('Price must be a valid positive number.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const qParams = brandId ? { brand_id: brandId } : {}
      const body = {
        name,
        description: description || null,
        base_price_cents: priceCents,
        category_id: categoryId,
        is_taxable: taxable,
      }
      if (product) {
        await api.patch(`/products/${product.id}`, body, { params: qParams })
      } else {
        await api.post('/products', body, { params: qParams })
      }
      onSaved()
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'Failed to save product.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title={product ? 'Edit product' : 'Add product'} onClose={onClose}>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {taxable ? 'Price ($, tax-inclusive)' : 'Price ($, no tax)'}
          </label>
          <input
            type="number"
            step="0.01"
            min="0"
            value={priceStr}
            onChange={(e) => setPriceStr(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          {product && taxable && (
            <p className="text-xs text-gray-400 mt-1">
              Tax-exclusive price (auto-calculated): {centsToDisplay(product.price_ex_cents)}
            </p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
          <select
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Tax</label>
          <select
            value={taxable ? 'taxed' : 'free'}
            onChange={(e) => handleTaxableChange(e.target.value === 'taxed')}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="taxed">Taxed (sold at inclusive price)</option>
            <option value="free">Tax free (no tax applied)</option>
          </select>
          <p className="text-xs text-gray-400 mt-1">
            {taxable
              ? 'The tax rate is set by the administrator per country and used to split the inclusive price.'
              : 'No tax is applied — the price above is charged exactly as entered.'}
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>

        {error && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900">
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !name}
            className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

