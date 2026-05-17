/** Tax categories and rates management page. */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { Modal } from '../../components/Modal'
import { StatusBadge } from '../../components/StatusBadge'
import type { TaxCategory, TaxRate } from '../../types'

export function TaxPage() {
  const qc = useQueryClient()
  const brandId = useMgmtBrandId()
  const [showCreateCat, setShowCreateCat] = useState(false)
  const [selectedCat, setSelectedCat] = useState<TaxCategory | null>(null)
  const [showCreateRate, setShowCreateRate] = useState(false)

  const params = brandId ? { brand_id: brandId } : {}

  const { data: taxCategories = [], isLoading } = useQuery<TaxCategory[]>({
    queryKey: ['tax-categories', brandId],
    queryFn: () => api.get('/tax/categories', { params }).then((r) => r.data),
    enabled: brandId !== undefined,
  })

  const { data: rates = [] } = useQuery<TaxRate[]>({
    queryKey: ['tax-rates', selectedCat?.id],
    queryFn: () =>
      api.get('/tax/rates', { params: { tax_category_id: selectedCat!.id } }).then((r) => r.data),
    enabled: !!selectedCat,
  })

  const deactivateCat = useMutation({
    mutationFn: (id: string) => api.patch(`/tax/categories/${id}`, { is_active: false }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tax-categories', brandId] }),
  })

  if (!brandId) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-gray-400">
        No brand context available.
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      {/* Tax categories */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-semibold text-gray-900">Tax categories</h1>
          <button
            onClick={() => setShowCreateCat(true)}
            className="px-3 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition-colors"
          >
            Add category
          </button>
        </div>

        {isLoading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {taxCategories.map((c) => (
                  <tr
                    key={c.id}
                    className={`hover:bg-gray-50 cursor-pointer ${selectedCat?.id === c.id ? 'bg-indigo-50' : ''}`}
                    onClick={() => setSelectedCat(c.id === selectedCat?.id ? null : c)}
                  >
                    <td className="px-4 py-3 font-medium text-gray-900">{c.name}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={c.is_active ? "active" : "disabled"} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      {c.is_active && (
                        <button
                          onClick={(e) => { e.stopPropagation(); deactivateCat.mutate(c.id) }}
                          className="text-red-500 hover:text-red-700 text-xs font-medium"
                        >
                          Deactivate
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {taxCategories.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-4 py-8 text-center text-gray-400">
                      No tax categories yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Rates for selected category */}
      {selectedCat && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-medium text-gray-800">
              Rates — {selectedCat.name}
            </h2>
            <button
              onClick={() => setShowCreateRate(true)}
              className="px-3 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition-colors"
            >
              Add rate
            </button>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Rate %</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Model</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rates.map((r) => (
                  <tr key={r.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">{r.name}</td>
                    <td className="px-4 py-3 text-gray-700">{r.rate_percent}%</td>
                    <td className="px-4 py-3 text-gray-500 capitalize">{r.tax_model}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={r.is_active ? "active" : "disabled"} />
                    </td>
                  </tr>
                ))}
                {rates.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-gray-400">
                      No rates for this category.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showCreateCat && (
        <TaxCategoryFormModal
          brandId={brandId}
          onClose={() => setShowCreateCat(false)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ['tax-categories', brandId] })
            setShowCreateCat(false)
          }}
        />
      )}

      {showCreateRate && selectedCat && (
        <TaxRateFormModal
          taxCategoryId={selectedCat.id}
          onClose={() => setShowCreateRate(false)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ['tax-rates', selectedCat.id] })
            setShowCreateRate(false)
          }}
        />
      )}
    </div>
  )
}

// ── Tax category form ──────────────────────────────────────────────────────────

function TaxCategoryFormModal({ brandId, onClose, onSaved }: { brandId: string; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await api.post('/tax/categories', { name, brand_id: brandId })
      onSaved()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Failed to save.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="Add tax category" onClose={onClose}>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        {error && <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900">Cancel</button>
          <button
            onClick={handleSave}
            disabled={saving || !name}
            className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

// ── Tax rate form ──────────────────────────────────────────────────────────────

function TaxRateFormModal({ taxCategoryId, onClose, onSaved }: { taxCategoryId: string; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState('')
  const [rate, setRate] = useState('')
  const [model, setModel] = useState<'exclusive' | 'inclusive' | 'compound'>('exclusive')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await api.post('/tax/rates', {
        name,
        rate_percent: rate,
        tax_model: model,
        tax_category_id: taxCategoryId,
      })
      onSaved()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Failed to save.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="Add tax rate" onClose={onClose}>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Rate (%)</label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={rate}
              onChange={(e) => setRate(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value as typeof model)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="exclusive">Exclusive</option>
              <option value="inclusive">Inclusive</option>
              <option value="compound">Compound</option>
            </select>
          </div>
        </div>
        {error && <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900">Cancel</button>
          <button
            onClick={handleSave}
            disabled={saving || !name || !rate}
            className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
