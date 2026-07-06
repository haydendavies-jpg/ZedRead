/** Catalog products management page — list, create, edit, deactivate products. */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { Modal } from '../../components/Modal'
import { StatusBadge } from '../../components/StatusBadge'
import type { Product, Category } from '../../types'

function centsToDisplay(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

export function ProductsPage() {
  const qc = useQueryClient()
  const brandId = useMgmtBrandId()
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<Product | null>(null)

  const params = brandId ? { brand_id: brandId } : {}

  const { data: products = [], isLoading } = useQuery<Product[]>({
    queryKey: ['products', brandId],
    queryFn: () => api.get('/products', { params }).then((r) => r.data),
    enabled: brandId !== undefined,
  })

  const { data: categories = [] } = useQuery<Category[]>({
    queryKey: ['categories', brandId],
    queryFn: () => api.get('/categories', { params }).then((r) => r.data),
    enabled: !!brandId,
  })

  const deactivate = useMutation({
    mutationFn: (id: string) =>
      api.delete(`/products/${id}`, { params }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['products', brandId] }),
  })

  if (!brandId) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-gray-400">
        No brand context available. Use a brand-scope management token or select a brand.
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Products</h1>
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
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm min-w-[500px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Price (inc.)</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Price (ex.)</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Tax</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {products.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{p.name}</td>
                  <td className="px-4 py-3 text-gray-700">{centsToDisplay(p.base_price_cents)}</td>
                  <td className="px-4 py-3 text-gray-500">{centsToDisplay(p.price_ex_cents)}</td>
                  <td className="px-4 py-3">
                    {p.is_taxable ? (
                      <span className="text-xs text-gray-700">Taxed</span>
                    ) : (
                      <span className="text-xs text-gray-500">Tax free</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={p.is_active ? "active" : "disabled"} />
                  </td>
                  <td className="px-4 py-3 text-right space-x-2">
                    <button
                      onClick={() => setEditing(p)}
                      className="text-brand-600 hover:text-brand-800 text-xs font-medium"
                    >
                      Edit
                    </button>
                    {p.is_active && (
                      <button
                        onClick={() => deactivate.mutate(p.id)}
                        className="text-red-500 hover:text-red-700 text-xs font-medium"
                      >
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {products.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                    No products yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {(showCreate || editing) && (
        <ProductFormModal
          product={editing}
          brandId={brandId}
          categories={categories}
          onClose={() => { setShowCreate(false); setEditing(null) }}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ['products', brandId] })
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
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Failed to save product.')
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
