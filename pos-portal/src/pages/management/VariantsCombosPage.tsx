/**
 * Combined Variants + Combos management page (Stage 22) — one sidebar entry with
 * two tabs, matching the "one combined portal page" resolution in STAGE_PLAN_16-24.md.
 * Modifiers are deliberately excluded — they stay edited inline on the Product page.
 *
 * Variants have no create flow here: creating one requires assigning per-brand
 * attribute type/value combinations, and no portal page manages attribute types
 * yet (that was never built when Stage 9 shipped the backend). Browsing,
 * filtering, inline edit (display name/SKU/price), status toggle, and
 * update-only import/export are all supported — see import_service.py's
 * import_variants() for why creation-by-import isn't supported either.
 */

import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { Modal } from '../../components/Modal'
import { StatusBadge } from '../../components/StatusBadge'
import { EntityIdChip } from '../../components/EntityIdChip'
import { EditableText } from '../../components/EditableCell'
import { FilterBar, type FilterConfig } from '../../components/FilterBar'
import { downloadBlob } from '../../utils/download'
import { apiErrorMessage } from '../../utils/apiError'
import type { ComboGroupListItem, ProductListItem, VariantListItem } from '../../types'

function centsToDisplay(cents: number | null): string {
  return cents === null ? '—' : `$${(cents / 100).toFixed(2)}`
}

interface ImportSummary {
  import_id: string
  created: number
  updated: number
  errors: { row_number: number; message: string }[]
}

type Tab = 'variants' | 'combos'

export function VariantsCombosPage() {
  const brandId = useMgmtBrandId()
  const [tab, setTab] = useState<Tab>('variants')

  if (!brandId) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-gray-400">
        No brand context available.
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-gray-900">Variants &amp; Combos</h1>
      </div>

      <div className="flex gap-1 border-b border-gray-200">
        {(['variants', 'combos'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize border-b-2 -mb-px transition-colors ${
              tab === t ? 'border-brand-600 text-brand-800' : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'variants' ? <VariantsTab brandId={brandId} /> : <CombosTab brandId={brandId} />}
    </div>
  )
}

// ── Shared import/export bar ────────────────────────────────────────────────────

interface ImportExportBarProps {
  resource: 'variants' | 'combos'
  brandId: string
  onImported: () => void
}

function ImportExportBar({ resource, brandId, onImported }: ImportExportBarProps) {
  const params = { brand_id: brandId }
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [summary, setSummary] = useState<ImportSummary | null>(null)

  const download = async (path: string, filename: string) => {
    setBusy(true)
    setError(null)
    try {
      const resp = await api.get(path, { params, responseType: 'blob' })
      downloadBlob(resp.data, filename)
    } catch {
      setError(`Failed to download ${filename}.`)
    } finally {
      setBusy(false)
    }
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setBusy(true)
    setError(null)
    setSummary(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await api.post(`/${resource}/import`, formData, { params })
      setSummary(resp.data)
      onImported()
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'Import failed.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        onClick={() => download(`/${resource}/export/template`, `${resource}_template.xlsx`)}
        disabled={busy}
        className="text-xs px-3 py-1.5 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
      >
        Download template
      </button>
      <button
        onClick={() => download(`/${resource}/export`, `${resource}_export.xlsx`)}
        disabled={busy}
        className="text-xs px-3 py-1.5 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
      >
        Export XLSX
      </button>
      <button
        onClick={() => fileInputRef.current?.click()}
        disabled={busy}
        className="text-xs px-3 py-1.5 bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors"
      >
        {busy ? 'Working…' : 'Import XLSX'}
      </button>
      <input ref={fileInputRef} type="file" accept=".xlsx" className="hidden" onChange={handleFileChange} />
      {error && <p className="text-xs text-red-600">{error}</p>}
      {summary && (
        <p className="text-xs text-gray-500">
          {summary.created} created, {summary.updated} updated
          {summary.errors.length > 0 && `, ${summary.errors.length} row(s) skipped: ${summary.errors.map((e) => `#${e.row_number} ${e.message}`).join('; ')}`}
        </p>
      )}
    </div>
  )
}

// ── Variants tab ─────────────────────────────────────────────────────────────────

function VariantsTab({ brandId }: { brandId: string }) {
  const qc = useQueryClient()
  const params = { brand_id: brandId }

  const [search, setSearch] = useState('')
  const [productFilter, setProductFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const { data: variants = [], isLoading } = useQuery<VariantListItem[]>({
    queryKey: ['variants', brandId],
    queryFn: () => api.get('/variants', { params: { ...params, include_inactive: true, limit: 200 } }).then((r) => r.data),
  })

  const { data: products = [] } = useQuery<ProductListItem[]>({
    queryKey: ['products', brandId],
    queryFn: () => api.get('/products', { params: { ...params, limit: 200 } }).then((r) => r.data),
  })

  const invalidateList = () => qc.invalidateQueries({ queryKey: ['variants', brandId] })

  const patch = useMutation({
    mutationFn: ({ variant, body }: { variant: VariantListItem; body: Record<string, unknown> }) =>
      api.patch(`/products/${variant.product_id}/variants/${variant.id}`, body, { params }),
    onSuccess: invalidateList,
    onError: invalidateList,
  })

  const deactivate = useMutation({
    mutationFn: (variant: VariantListItem) =>
      api.delete(`/products/${variant.product_id}/variants/${variant.id}`, { params }),
    onSuccess: invalidateList,
    onError: invalidateList,
  })

  const activate = useMutation({
    mutationFn: (variant: VariantListItem) =>
      api.post(`/products/${variant.product_id}/variants/${variant.id}/activate`, {}, { params }),
    onSuccess: invalidateList,
    onError: invalidateList,
  })

  const filtered = variants.filter((v) => {
    const label = v.display_name || v.sku || ''
    if (search && !label.toLowerCase().includes(search.toLowerCase()) && !v.ref.toLowerCase().includes(search.toLowerCase())) return false
    if (productFilter && v.product_id !== productFilter) return false
    if (statusFilter === 'active' && !v.is_active) return false
    if (statusFilter === 'inactive' && v.is_active) return false
    return true
  })

  const hasFilters = !!(search || productFilter || statusFilter)
  const clearFilters = () => { setSearch(''); setProductFilter(''); setStatusFilter('') }

  const filters: FilterConfig[] = [
    {
      label: 'Product',
      value: productFilter,
      onChange: setProductFilter,
      options: [{ value: '', label: 'All products' }, ...products.map((p) => ({ value: p.id, label: p.name }))],
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

  return (
    <div className="space-y-4">
      <ImportExportBar resource="variants" brandId={brandId} onImported={invalidateList} />

      {isLoading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : (
        <>
          <FilterBar
            search={search}
            onSearchChange={setSearch}
            searchPlaceholder="Search by display name, SKU, or code…"
            filters={filters}
            hasFilters={hasFilters}
            onClear={clearFilters}
            resultCount={filtered.length}
            totalCount={variants.length}
          />

          <div className="overflow-x-auto rounded-xl border border-gray-200">
            <table className="w-full text-sm min-w-[800px]">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">ID</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Display Name</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Linked Product</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">SKU</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Price</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map((v) => (
                  <tr key={v.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3"><EntityIdChip id={v.id} ref={v.ref} /></td>
                    <td className="px-4 py-3 font-medium text-gray-900">
                      <EditableText
                        value={v.display_name ?? ''}
                        emptyLabel="Set a name…"
                        onSave={async (val) => { await patch.mutateAsync({ variant: v, body: { display_name: val || null } }) }}
                      />
                    </td>
                    <td className="px-4 py-3 text-gray-700">
                      <EntityIdChip id={v.product_id} ref={v.product_ref} /> <span className="ml-1">{v.product_name}</span>
                    </td>
                    <td className="px-4 py-3 text-gray-700">
                      <EditableText
                        value={v.sku ?? ''}
                        emptyLabel="—"
                        onSave={async (val) => { await patch.mutateAsync({ variant: v, body: { sku: val || null } }) }}
                      />
                    </td>
                    <td className="px-4 py-3 text-gray-700">
                      <EditableText
                        value={v.price_cents !== null ? (v.price_cents / 100).toFixed(2) : ''}
                        type="number"
                        emptyLabel="Inherits product price"
                        formatDisplay={() => centsToDisplay(v.price_cents)}
                        onSave={async (val) => {
                          if (!val) {
                            await patch.mutateAsync({ variant: v, body: { price_cents: null } })
                            return
                          }
                          const cents = Math.round(parseFloat(val) * 100)
                          if (isNaN(cents) || cents < 0) throw new Error('Price must be a valid positive number.')
                          await patch.mutateAsync({ variant: v, body: { price_cents: cents } })
                        }}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge
                        status={v.is_active ? 'active' : 'disabled'}
                        title={v.is_active ? 'Click to deactivate' : 'Click to activate'}
                        onClick={() => (v.is_active ? deactivate.mutate(v) : activate.mutate(v))}
                      />
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                      {variants.length === 0 ? 'No variants yet.' : 'No variants match the current filters.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

// ── Combos tab ───────────────────────────────────────────────────────────────────

function CombosTab({ brandId }: { brandId: string }) {
  const qc = useQueryClient()
  const params = { brand_id: brandId }
  const [showCreate, setShowCreate] = useState(false)

  const [search, setSearch] = useState('')
  const [productFilter, setProductFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const { data: combos = [], isLoading } = useQuery<ComboGroupListItem[]>({
    queryKey: ['combos', brandId],
    queryFn: () => api.get('/combos', { params: { ...params, include_inactive: true, limit: 200 } }).then((r) => r.data),
  })

  const { data: products = [] } = useQuery<ProductListItem[]>({
    queryKey: ['products', brandId],
    queryFn: () => api.get('/products', { params: { ...params, limit: 200 } }).then((r) => r.data),
  })

  const invalidateList = () => qc.invalidateQueries({ queryKey: ['combos', brandId] })

  const patch = useMutation({
    mutationFn: ({ combo, body }: { combo: ComboGroupListItem; body: Record<string, unknown> }) =>
      api.patch(`/products/${combo.product_id}/combos/groups/${combo.id}`, body, { params }),
    onSuccess: invalidateList,
    onError: invalidateList,
  })

  const deactivate = useMutation({
    mutationFn: (combo: ComboGroupListItem) =>
      api.delete(`/products/${combo.product_id}/combos/groups/${combo.id}`, { params }),
    onSuccess: invalidateList,
    onError: invalidateList,
  })

  const activate = useMutation({
    mutationFn: (combo: ComboGroupListItem) =>
      api.post(`/products/${combo.product_id}/combos/groups/${combo.id}/activate`, {}, { params }),
    onSuccess: invalidateList,
    onError: invalidateList,
  })

  const filtered = combos.filter((c) => {
    const label = c.display_name || c.name
    if (search && !label.toLowerCase().includes(search.toLowerCase()) && !c.ref.toLowerCase().includes(search.toLowerCase())) return false
    if (productFilter && c.product_id !== productFilter) return false
    if (statusFilter === 'active' && !c.is_active) return false
    if (statusFilter === 'inactive' && c.is_active) return false
    return true
  })

  const hasFilters = !!(search || productFilter || statusFilter)
  const clearFilters = () => { setSearch(''); setProductFilter(''); setStatusFilter('') }

  const filters: FilterConfig[] = [
    {
      label: 'Product',
      value: productFilter,
      onChange: setProductFilter,
      options: [{ value: '', label: 'All products' }, ...products.map((p) => ({ value: p.id, label: p.name }))],
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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ImportExportBar resource="combos" brandId={brandId} onImported={invalidateList} />
        <button
          onClick={() => setShowCreate(true)}
          className="px-3 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
        >
          Add combo
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : (
        <>
          <FilterBar
            search={search}
            onSearchChange={setSearch}
            searchPlaceholder="Search by display name, name, or code…"
            filters={filters}
            hasFilters={hasFilters}
            onClear={clearFilters}
            resultCount={filtered.length}
            totalCount={combos.length}
          />

          <div className="overflow-x-auto rounded-xl border border-gray-200">
            <table className="w-full text-sm min-w-[800px]">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">ID</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Display Name</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Internal Name</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Linked Product</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Selections</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map((c) => (
                  <tr key={c.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3"><EntityIdChip id={c.id} ref={c.ref} /></td>
                    <td className="px-4 py-3 font-medium text-gray-900">
                      <EditableText
                        value={c.display_name ?? ''}
                        emptyLabel="Set a name…"
                        onSave={async (val) => { await patch.mutateAsync({ combo: c, body: { display_name: val || null } }) }}
                      />
                    </td>
                    <td className="px-4 py-3 text-gray-700">
                      <EditableText
                        value={c.name}
                        onSave={async (val) => { await patch.mutateAsync({ combo: c, body: { name: val } }) }}
                      />
                    </td>
                    <td className="px-4 py-3 text-gray-700">
                      <EntityIdChip id={c.product_id} ref={c.product_ref} /> <span className="ml-1">{c.product_name}</span>
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {c.min_selections}–{c.max_selections} {c.is_required ? '(required)' : '(optional)'}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge
                        status={c.is_active ? 'active' : 'disabled'}
                        title={c.is_active ? 'Click to deactivate' : 'Click to activate'}
                        onClick={() => (c.is_active ? deactivate.mutate(c) : activate.mutate(c))}
                      />
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                      {combos.length === 0 ? 'No combos yet.' : 'No combos match the current filters.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {showCreate && (
        <ComboCreateModal
          brandId={brandId}
          products={products}
          onClose={() => setShowCreate(false)}
          onSaved={() => { invalidateList(); setShowCreate(false) }}
        />
      )}
    </div>
  )
}

interface ComboCreateModalProps {
  brandId: string
  products: ProductListItem[]
  onClose: () => void
  onSaved: () => void
}

function ComboCreateModal({ brandId, products, onClose, onSaved }: ComboCreateModalProps) {
  const [productId, setProductId] = useState(products[0]?.id ?? '')
  const [name, setName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [minSelections, setMinSelections] = useState('1')
  const [maxSelections, setMaxSelections] = useState('1')
  const [isRequired, setIsRequired] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await api.post(
        `/products/${productId}/combos/groups`,
        {
          name,
          display_name: displayName || null,
          min_selections: parseInt(minSelections, 10) || 0,
          max_selections: parseInt(maxSelections, 10) || 1,
          is_required: isRequired,
        },
        { params: { brand_id: brandId } }
      )
      onSaved()
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'Failed to save combo.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="Add combo" onClose={onClose}>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Product</label>
          <select
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="" disabled>Select a product…</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Internal name (POS-facing)</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Choose a side"
            autoFocus
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Display name (management-facing, optional)</label>
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        <div className="flex gap-3">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">Min selections</label>
            <input
              type="number"
              min={0}
              value={minSelections}
              onChange={(e) => setMinSelections(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">Max selections</label>
            <input
              type="number"
              min={1}
              value={maxSelections}
              onChange={(e) => setMaxSelections(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input type="checkbox" checked={isRequired} onChange={(e) => setIsRequired(e.target.checked)} />
          Required — the cashier must select at least one option
        </label>
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
            disabled={saving || !name || !productId}
            className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
