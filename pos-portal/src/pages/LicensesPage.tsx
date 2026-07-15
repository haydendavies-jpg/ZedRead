/** Licenses management page — list, create, disable/enable. */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, fetchAll } from '../api/axios'
import type { License, Site } from '../types'
import { EntityIdChip } from '../components/EntityIdChip'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'

async function fetchLicenses(): Promise<License[]> {
  return fetchAll<License>('/licenses/')
}

async function fetchSites(): Promise<Site[]> {
  return fetchAll<Site>('/sites/')
}

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

export function LicensesPage() {
  const qc = useQueryClient()
  const { data: licenses = [], isLoading } = useQuery({ queryKey: ['licenses'], queryFn: fetchLicenses })
  const { data: sites = [] } = useQuery({ queryKey: ['sites'], queryFn: fetchSites })

  const [siteFilter, setSiteFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [trialFilter, setTrialFilter] = useState('')

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({
    site_id: '',
    plan_name: '',
    monthly_fee_cents: '0',
    is_trial: false,
    starts_at: '',
    expires_at: '',
  })
  const [formError, setFormError] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['licenses'] })

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.post('/licenses/', payload),
    onSuccess: () => {
      invalidate()
      setShowCreate(false)
      setForm({ site_id: '', plan_name: '', monthly_fee_cents: '0', is_trial: false, starts_at: '', expires_at: '' })
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setFormError(msg ?? 'Failed to create license.')
    },
  })

  const disableMutation = useMutation({
    mutationFn: (id: string) => api.post(`/licenses/${id}/disable`),
    onSuccess: invalidate,
  })

  const enableMutation = useMutation({
    mutationFn: (id: string) => api.post(`/licenses/${id}/enable`),
    onSuccess: invalidate,
  })

  const siteName = (id: string) => sites.find((s) => s.id === id)?.name ?? id.slice(0, 8)

  const openCreate = () => {
    setForm({ site_id: sites[0]?.id ?? '', plan_name: 'starter', monthly_fee_cents: '9900', is_trial: false, starts_at: '', expires_at: '' })
    setFormError(null)
    setShowCreate(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    createMutation.mutate({
      ...form,
      monthly_fee_cents: parseInt(form.monthly_fee_cents, 10),
    })
  }

  const filtered = licenses.filter((l) => {
    if (siteFilter && l.site_id !== siteFilter) return false
    if (statusFilter && l.status !== statusFilter) return false
    if (trialFilter === 'trial' && !l.is_trial) return false
    if (trialFilter === 'paid' && l.is_trial) return false
    return true
  })

  const hasFilters = siteFilter || statusFilter || trialFilter

  return (
    <div className="p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Licenses</h1>
        <button
          onClick={openCreate}
          className="bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New License
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <select
          value={siteFilter}
          onChange={(e) => setSiteFilter(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">All sites</option>
          {sites.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="disabled">Disabled</option>
          <option value="expired">Expired</option>
        </select>
        <select
          value={trialFilter}
          onChange={(e) => setTrialFilter(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">Trial &amp; paid</option>
          <option value="trial">Trial only</option>
          <option value="paid">Paid only</option>
        </select>
        {hasFilters && (
          <button
            onClick={() => { setSiteFilter(''); setStatusFilter(''); setTrialFilter('') }}
            className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600"
          >
            Clear filters
          </button>
        )}
        <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">
          {filtered.length} of {licenses.length}
        </span>
      </div>

      {isLoading ? (
        <div className="text-gray-400 dark:text-gray-500 text-sm">Loading…</div>
      ) : (
        <div className="zr-table-wrap">
          <table className="zr-table min-w-[640px]">
            <thead>
              <tr>
                <th>ID</th>
                <th>Site</th>
                <th>Plan</th>
                <th className="zr-num">Monthly Fee</th>
                <th>Expires</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((l) => (
                <tr key={l.id}>
                  <td><EntityIdChip id={l.id} /></td>
                  <td className="text-[var(--zr-muted)]">{siteName(l.site_id)}</td>
                  <td className="font-medium">
                    {l.plan_name}
                    {l.is_trial && <span className="ml-1 text-xs text-brand-500">(trial)</span>}
                  </td>
                  <td className="zr-num font-mono">{formatCents(l.monthly_fee_cents)}</td>
                  <td className="text-[var(--zr-muted)]">{new Date(l.expires_at).toLocaleDateString()}</td>
                  <td><StatusBadge status={l.status} /></td>
                  <td className="zr-cell-pad">
                    <div className="flex flex-wrap items-center gap-2">
                      {l.status === 'active' && (
                        <button onClick={() => disableMutation.mutate(l.id)} className="text-amber-600 hover:underline text-xs">Disable</button>
                      )}
                      {l.status === 'disabled' && (
                        <button onClick={() => enableMutation.mutate(l.id)} className="text-green-600 hover:underline text-xs">Enable</button>
                      )}
                      {l.status === 'expired' && (
                        <span className="text-xs text-[var(--zr-faint)]">Expired</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={7} className="text-center text-[var(--zr-faint)] py-8">
                  {licenses.length === 0 ? 'No licenses yet.' : 'No licenses match the current filters.'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <Modal title="New License" onClose={() => setShowCreate(false)}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Site</label>
              <select
                value={form.site_id}
                onChange={(e) => setForm({ ...form, site_id: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Plan Name</label>
              <input
                value={form.plan_name}
                onChange={(e) => setForm({ ...form, plan_name: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="starter"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Monthly Fee (cents)</label>
              <input
                type="number"
                min={0}
                value={form.monthly_fee_cents}
                onChange={(e) => setForm({ ...form, monthly_fee_cents: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Starts At</label>
                <input
                  type="datetime-local"
                  value={form.starts_at}
                  onChange={(e) => setForm({ ...form, starts_at: e.target.value })}
                  required
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Expires At</label>
                <input
                  type="datetime-local"
                  value={form.expires_at}
                  onChange={(e) => setForm({ ...form, expires_at: e.target.value })}
                  required
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_trial}
                onChange={(e) => setForm({ ...form, is_trial: e.target.checked })}
                className="rounded"
              />
              Trial license
            </label>
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800">Cancel</button>
              <button type="submit" disabled={createMutation.isPending} className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg">Create</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
