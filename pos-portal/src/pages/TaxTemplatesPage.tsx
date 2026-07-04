/**
 * SuperAdmin-only page for jurisdiction-scoped tax templates.
 *
 * Templates define the tax rates that apply to sites by location
 * (country → state → county → city; unset fields apply at the wider level).
 * At sale time the invoice engine resolves a site's rates from every matching
 * template — customers never configure tax, they only mark products taxed or
 * tax free.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/axios'
import type { TaxTemplate, TaxTemplateRate } from '../types'
import { Modal } from '../components/Modal'
import { apiErrorMessage } from '../utils/apiError'

async function fetchTaxTemplates(): Promise<TaxTemplate[]> {
  const { data } = await api.get('/admin/tax-templates/', { params: { limit: 200 } })
  return data
}

const DEFAULT_TEMPLATE_FORM = { name: '', country: '', state: '', county: '', city: '' }
const DEFAULT_RATE_FORM = { name: '', rate_percent: '', tax_model: 'inclusive' as TaxTemplateRate['tax_model'] }

/** Human-readable jurisdiction summary, e.g. "AU" or "US · TX · Travis". */
function jurisdiction(t: TaxTemplate): string {
  return [t.country, t.state, t.county, t.city].filter(Boolean).join(' · ')
}

export function TaxTemplatesPage() {
  const qc = useQueryClient()
  const { data: templates = [], isLoading } = useQuery({ queryKey: ['tax-templates'], queryFn: fetchTaxTemplates })

  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<TaxTemplate | null>(null)
  const [form, setForm] = useState(DEFAULT_TEMPLATE_FORM)
  const [formError, setFormError] = useState<string | null>(null)
  const [addingRateFor, setAddingRateFor] = useState<TaxTemplate | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['tax-templates'] })

  const createMutation = useMutation({
    mutationFn: (body: typeof DEFAULT_TEMPLATE_FORM) =>
      api.post('/admin/tax-templates/', {
        name: body.name,
        country: body.country.toUpperCase(),
        state: body.state || null,
        county: body.county || null,
        city: body.city || null,
      }),
    onSuccess: () => { invalidate(); setShowCreate(false); setForm(DEFAULT_TEMPLATE_FORM) },
    onError: (e: unknown) => { invalidate(); setFormError(apiErrorMessage(e, 'Failed to create tax template.')) },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: typeof DEFAULT_TEMPLATE_FORM }) =>
      api.patch(`/admin/tax-templates/${id}`, {
        name: body.name,
        country: body.country.toUpperCase(),
        state: body.state || null,
        county: body.county || null,
        city: body.city || null,
      }),
    onSuccess: () => { invalidate(); setEditing(null) },
    onError: (e: unknown) => { invalidate(); setFormError(apiErrorMessage(e, 'Failed to update tax template.')) },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/admin/tax-templates/${id}`),
    onSuccess: invalidate,
    onError: invalidate,
  })

  const deleteRateMutation = useMutation({
    mutationFn: (rateId: string) => api.delete(`/admin/tax-templates/rates/${rateId}`),
    onSuccess: invalidate,
    onError: invalidate,
  })

  const openCreate = () => { setForm(DEFAULT_TEMPLATE_FORM); setFormError(null); setShowCreate(true) }
  const openEdit = (t: TaxTemplate) => {
    setForm({ name: t.name, country: t.country, state: t.state ?? '', county: t.county ?? '', city: t.city ?? '' })
    setFormError(null)
    setEditing(t)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    if (editing) updateMutation.mutate({ id: editing.id, body: form })
    else createMutation.mutate(form)
  }

  return (
    <div className="p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
        <h1 className="text-xl font-semibold text-gray-900">Tax Templates</h1>
        <button
          onClick={openCreate}
          className="bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New Template
        </button>
      </div>
      <p className="text-sm text-gray-500 mb-4 max-w-2xl">
        Rates apply to a site when every set field matches its location. Leave state/county/city blank
        to apply at a wider level (e.g. country only for Australia). Sites resolve and combine all
        matching templates automatically at sale time.
      </p>

      {isLoading ? (
        <div className="text-gray-400 text-sm">Loading…</div>
      ) : templates.length === 0 ? (
        <div className="text-gray-400 text-sm rounded-xl border border-gray-200 px-4 py-8 text-center">
          No tax templates yet.
        </div>
      ) : (
        <div className="space-y-4">
          {templates.map((t) => (
            <div key={t.id} className="rounded-xl border border-gray-200 bg-white p-4 sm:p-6">
              <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
                <div>
                  <p className="font-medium text-gray-900">{t.name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{jurisdiction(t)}</p>
                </div>
                <div className="flex flex-wrap gap-3 text-xs">
                  <button onClick={() => setAddingRateFor(t)} className="text-brand-600 hover:underline">Add rate</button>
                  <button onClick={() => openEdit(t)} className="text-brand-600 hover:underline">Edit</button>
                  <button
                    onClick={() => { if (confirm(`Delete tax template "${t.name}"?`)) deleteMutation.mutate(t.id) }}
                    className="text-red-500 hover:underline"
                  >
                    Delete
                  </button>
                </div>
              </div>

              <div className="overflow-x-auto rounded-lg border border-gray-100">
                <table className="w-full text-sm min-w-[420px]">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      <th className="px-3 py-2">Rate</th>
                      <th className="px-3 py-2">Percent</th>
                      <th className="px-3 py-2">Model</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {t.rates.map((r) => (
                      <tr key={r.id}>
                        <td className="px-3 py-2 text-gray-900">{r.name}</td>
                        <td className="px-3 py-2 text-gray-700">{Number(r.rate_percent)}%</td>
                        <td className="px-3 py-2 text-gray-500 capitalize">{r.tax_model}</td>
                        <td className="px-3 py-2 text-right">
                          <button
                            onClick={() => deleteRateMutation.mutate(r.id)}
                            className="text-red-500 hover:underline text-xs"
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                    {t.rates.length === 0 && (
                      <tr><td colSpan={4} className="px-3 py-4 text-center text-gray-400 text-xs">No rates — add one.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}

      {(showCreate || editing) && (
        <Modal title={editing ? 'Edit Tax Template' : 'New Tax Template'} onClose={() => { setShowCreate(false); setEditing(null) }}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
                autoFocus
                placeholder="Australia GST"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Country (ISO 2-letter)</label>
              <input
                value={form.country}
                onChange={(e) => setForm({ ...form, country: e.target.value })}
                required
                minLength={2}
                maxLength={2}
                placeholder="AU"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm uppercase focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">State</label>
                <input value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value })} placeholder="Optional" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">County</label>
                <input value={form.county} onChange={(e) => setForm({ ...form, county: e.target.value })} placeholder="Optional" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">City</label>
                <input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} placeholder="Optional" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
              </div>
            </div>
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => { setShowCreate(false); setEditing(null) }} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">Cancel</button>
              <button type="submit" disabled={createMutation.isPending || updateMutation.isPending} className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg">
                {editing ? 'Save' : 'Create'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {addingRateFor && (
        <AddRateModal template={addingRateFor} onClose={() => setAddingRateFor(null)} onSaved={() => { invalidate(); setAddingRateFor(null) }} />
      )}
    </div>
  )
}

// ── Add-rate modal ─────────────────────────────────────────────────────────────

function AddRateModal({ template, onClose, onSaved }: { template: TaxTemplate; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState(DEFAULT_RATE_FORM)
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () =>
      api.post(`/admin/tax-templates/${template.id}/rates`, {
        name: form.name,
        rate_percent: form.rate_percent,
        tax_model: form.tax_model,
      }),
    onSuccess: onSaved,
    onError: (e: unknown) => setError(apiErrorMessage(e, 'Failed to add rate.')),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    mutation.mutate()
  }

  return (
    <Modal title={`Add rate — ${template.name}`} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Rate name</label>
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required autoFocus placeholder="GST" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Percent</label>
          <input type="number" step="0.0001" min="0" max="100" value={form.rate_percent} onChange={(e) => setForm({ ...form, rate_percent: e.target.value })} required placeholder="10" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Tax model</label>
          <select value={form.tax_model} onChange={(e) => setForm({ ...form, tax_model: e.target.value as TaxTemplateRate['tax_model'] })} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500">
            <option value="inclusive">Inclusive (embedded in price)</option>
            <option value="exclusive">Exclusive (added on top)</option>
            <option value="compound">Compound (parallel to base)</option>
          </select>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">Cancel</button>
          <button type="submit" disabled={mutation.isPending} className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg">Add</button>
        </div>
      </form>
    </Modal>
  )
}
