/** Catalog products management page — list, create, edit, deactivate products.
 *
 * Stage 20: table shows joined Category + Reporting Group columns, supports
 * inline cell edit (name, category, price, status) and a shared filter bar.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, fetchAll } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { Modal } from '../../components/Modal'
import { StatusBadge } from '../../components/StatusBadge'
import { EntityIdChip } from '../../components/EntityIdChip'
import { EditableText, EditableSelect } from '../../components/EditableCell'
import { FilterBar, type FilterConfig } from '../../components/FilterBar'
import { apiErrorMessage } from '../../utils/apiError'
import type { Product, ProductListItem, Category, ReportingGroup } from '../../types'

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

          <div className="zr-table-wrap">
            <table className="zr-table min-w-[1000px]">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Category</th>
                  <th>Reporting Group</th>
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
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{p.reporting_group_name}</td>
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
                      {p.modifier_names ? (
                        <span className="inline-block max-w-[160px] truncate border border-brand-300 dark:border-brand-700 rounded-md px-2 py-1 text-xs text-gray-700 dark:text-gray-300" title={p.modifier_names}>
                          {p.modifier_names}
                        </span>
                      ) : (
                        <span className="inline-block border border-dashed border-gray-300 dark:border-gray-600 rounded-md px-2 py-1 text-xs text-gray-400 dark:text-gray-500">None</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge
                        status={p.is_active ? 'active' : 'disabled'}
                        title={p.is_active ? 'Click to deactivate' : 'Click to activate'}
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
                    <td colSpan={10} className="px-4 py-8 text-center text-gray-400">
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

