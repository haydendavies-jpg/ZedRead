/**
 * Site overrides page — view and adjust per-site product price overrides
 * and exclusions within the management user's brand.
 *
 * Brand/group scope management users and portal admins can access this page.
 * Site-scope users are blocked by ScopeGuard.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { ScopeGuard } from '../../components/ScopeGuard'
import { Modal } from '../../components/Modal'
import type { Site } from '../../types'

interface ResolvedProduct {
  product_id: string
  name: string
  category_id: string
  tax_category_id: string | null
  effective_price_cents: number
  photo_url: string | null
  display_order: number
  is_excluded: boolean
  override_price_cents: number | null
}

function centsToDisplay(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

export function SiteOverridesPage() {
  return (
    <ScopeGuard minScope="brand">
      <SiteOverridesInner />
    </ScopeGuard>
  )
}

function SiteOverridesInner() {
  const brandId = useMgmtBrandId()
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null)
  const [editingProduct, setEditingProduct] = useState<ResolvedProduct | null>(null)

  const qc = useQueryClient()
  const params = brandId ? { brand_id: brandId } : {}

  const { data: sites = [] } = useQuery<Site[]>({
    queryKey: ['sites-for-brand', brandId],
    queryFn: () => api.get('/sites', { params }).then((r) => r.data),
    enabled: !!brandId,
  })

  const { data: catalog = [], isLoading } = useQuery<ResolvedProduct[]>({
    queryKey: ['site-catalog', selectedSiteId, brandId],
    queryFn: () =>
      api.get(`/site-overrides/${selectedSiteId}/catalog`, { params }).then((r) => r.data),
    enabled: !!selectedSiteId,
  })

  const removeOverride = useMutation({
    mutationFn: (productId: string) =>
      api.delete(`/site-overrides/${selectedSiteId}/${productId}`, { params }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['site-catalog', selectedSiteId, brandId] }),
  })

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
        <h1 className="text-xl font-semibold text-gray-900">Site Overrides</h1>
        <div>
          <label className="text-xs text-gray-500 mr-2">Site</label>
          <select
            value={selectedSiteId ?? ''}
            onChange={(e) => setSelectedSiteId(e.target.value || null)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="">Select site…</option>
            {sites.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>
      </div>

      {!selectedSiteId ? (
        <div className="flex items-center justify-center h-40 text-sm text-gray-400">
          Select a site to manage its product overrides.
        </div>
      ) : isLoading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm min-w-[540px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Product</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">Base price</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">Site price</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {catalog.map((p) => (
                <tr key={p.product_id} className={p.is_excluded ? 'opacity-50' : 'hover:bg-gray-50'}>
                  <td className="px-4 py-3 font-medium text-gray-900">{p.name}</td>
                  <td className="px-4 py-3 text-right text-gray-500">
                    {centsToDisplay(p.effective_price_cents)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700">
                    {p.override_price_cents != null
                      ? <span className="font-medium text-brand-600">{centsToDisplay(p.override_price_cents)}</span>
                      : '—'
                    }
                  </td>
                  <td className="px-4 py-3">
                    {p.is_excluded ? (
                      <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full">excluded</span>
                    ) : (
                      <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">active</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right space-x-2">
                    <button
                      onClick={() => setEditingProduct(p)}
                      className="text-brand-600 hover:text-brand-800 text-xs font-medium"
                    >
                      Override
                    </button>
                    {(p.override_price_cents != null || p.is_excluded) && (
                      <button
                        onClick={() => removeOverride.mutate(p.product_id)}
                        className="text-gray-400 hover:text-red-600 text-xs font-medium"
                      >
                        Reset
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {catalog.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                    No products found for this site.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {editingProduct && selectedSiteId && (
        <OverrideFormModal
          product={editingProduct}
          siteId={selectedSiteId}
          brandId={brandId ?? undefined}
          onClose={() => setEditingProduct(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ['site-catalog', selectedSiteId, brandId] })
            setEditingProduct(null)
          }}
        />
      )}
    </div>
  )
}

interface OverrideFormProps {
  product: ResolvedProduct
  siteId: string
  brandId?: string
  onClose: () => void
  onSaved: () => void
}

function OverrideFormModal({ product, siteId, brandId, onClose, onSaved }: OverrideFormProps) {
  const [priceStr, setPriceStr] = useState(
    product.override_price_cents != null
      ? (product.override_price_cents / 100).toFixed(2)
      : ''
  )
  const [excluded, setExcluded] = useState(product.is_excluded)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const params = brandId ? { brand_id: brandId } : {}

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const overridePrice = priceStr ? Math.round(parseFloat(priceStr) * 100) : null
      await api.put(`/site-overrides/${siteId}/${product.product_id}`, {
        override_price_cents: overridePrice,
        is_excluded: excluded,
      }, { params })
      onSaved()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Failed to save override.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title={`Override — ${product.name}`} onClose={onClose}>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Override price ($) — leave blank to use brand price
          </label>
          <input
            type="number"
            step="0.01"
            min="0"
            value={priceStr}
            onChange={(e) => setPriceStr(e.target.value)}
            disabled={excluded}
            placeholder={`Base: ${(product.effective_price_cents / 100).toFixed(2)}`}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:bg-gray-50 disabled:text-gray-400"
          />
        </div>

        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={excluded}
            onChange={(e) => { setExcluded(e.target.checked); if (e.target.checked) setPriceStr('') }}
            className="w-4 h-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
          />
          <span className="text-sm text-gray-700">Exclude this product from this site</span>
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
            disabled={saving}
            className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save override'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
