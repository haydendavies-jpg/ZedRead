/**
 * POS Devices management page — register/deregister Android terminals.
 *
 * Registering a device is a prerequisite for the Android app's Login screen
 * to work at all (POST /auth/pos/login requires a device_token), and until
 * now the only way to do it was a raw API call — this is the first portal UI
 * for POST /pos-devices.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, fetchAll } from '../api/axios'
import type { PosDevice, License, Site } from '../types'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'

async function fetchDevices(): Promise<PosDevice[]> {
  return fetchAll<PosDevice>('/pos-devices/')
}

async function fetchSites(): Promise<Site[]> {
  return fetchAll<Site>('/sites/')
}

async function fetchLicenses(): Promise<License[]> {
  return fetchAll<License>('/licenses/')
}

/** A random 32-character hex token — a reasonable default for a device_token; still freely editable. */
function generateToken(): string {
  return crypto.randomUUID().replace(/-/g, '')
}

export function PosDevicesPage() {
  const qc = useQueryClient()
  const { data: devices = [], isLoading } = useQuery({ queryKey: ['pos-devices'], queryFn: fetchDevices })
  const { data: sites = [] } = useQuery({ queryKey: ['sites'], queryFn: fetchSites })
  const { data: licenses = [] } = useQuery({ queryKey: ['licenses'], queryFn: fetchLicenses })

  const [siteFilter, setSiteFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ site_id: '', license_id: '', device_name: '', device_token: '' })
  const [formError, setFormError] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['pos-devices'] })

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.post('/pos-devices/', payload),
    onSuccess: () => {
      invalidate()
      setShowCreate(false)
    },
    onError: (e: unknown) => {
      invalidate()
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setFormError(msg ?? 'Failed to register device.')
    },
  })

  const deregisterMutation = useMutation({
    mutationFn: (id: string) => api.post(`/pos-devices/${id}/deregister`),
    onSuccess: invalidate,
    onError: invalidate,
  })

  const siteName = (id: string) => sites.find((s) => s.id === id)?.name ?? id.slice(0, 8)

  const sitesLicenses = (siteId: string) => licenses.filter((l) => l.site_id === siteId)

  const openCreate = () => {
    const firstSite = sites[0]?.id ?? ''
    setForm({
      site_id: firstSite,
      license_id: sitesLicenses(firstSite)[0]?.id ?? '',
      device_name: '',
      device_token: generateToken(),
    })
    setFormError(null)
    setShowCreate(true)
  }

  const handleSiteChange = (siteId: string) => {
    setForm((f) => ({ ...f, site_id: siteId, license_id: sitesLicenses(siteId)[0]?.id ?? '' }))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    createMutation.mutate(form)
  }

  const handleCopy = async (id: string, token: string) => {
    await navigator.clipboard.writeText(token)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 1500)
  }

  const filtered = devices.filter((d) => {
    if (siteFilter && d.site_id !== siteFilter) return false
    if (statusFilter === 'active' && !d.is_active) return false
    if (statusFilter === 'inactive' && d.is_active) return false
    return true
  })

  const hasFilters = siteFilter || statusFilter

  return (
    <div className="p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">POS Devices</h1>
        <button
          onClick={openCreate}
          disabled={sites.length === 0}
          className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + Register Device
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
          <option value="">Any status</option>
          <option value="active">Active</option>
          <option value="inactive">Deregistered</option>
        </select>
        {hasFilters && (
          <button
            onClick={() => { setSiteFilter(''); setStatusFilter('') }}
            className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600"
          >
            Clear filters
          </button>
        )}
        <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">
          {filtered.length} of {devices.length}
        </span>
      </div>

      {isLoading ? (
        <div className="text-gray-400 dark:text-gray-500 text-sm">Loading…</div>
      ) : (
        <div className="zr-table-wrap">
          <table className="zr-table min-w-[760px]">
            <thead>
              <tr>
                <th>Device</th>
                <th>Site</th>
                <th>Device token</th>
                <th>Registered</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((d) => (
                <tr key={d.id}>
                  <td className="font-medium">{d.device_name}</td>
                  <td className="text-[var(--zr-muted)]">{siteName(d.site_id)}</td>
                  <td className="zr-cell-pad">
                    <button
                      onClick={() => handleCopy(d.id, d.device_token)}
                      title="Click to copy — paste into the app's Device Setup screen"
                      className="font-mono text-xs bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-600 dark:text-gray-300 px-2 py-0.5 rounded cursor-pointer transition-colors"
                    >
                      {copiedId === d.id ? '✓ copied' : d.device_token}
                    </button>
                  </td>
                  <td className="text-[var(--zr-muted)]">{new Date(d.registered_at).toLocaleDateString()}</td>
                  <td><StatusBadge status={d.is_active ? 'active' : 'inactive'} /></td>
                  <td className="zr-cell-pad">
                    {d.is_active ? (
                      <button
                        onClick={() => deregisterMutation.mutate(d.id)}
                        className="text-red-600 hover:underline text-xs"
                      >
                        Deregister
                      </button>
                    ) : (
                      <span className="text-xs text-[var(--zr-faint)]">Deregistered</span>
                    )}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={6} className="text-center text-[var(--zr-faint)] py-8">
                  {devices.length === 0 ? 'No devices registered yet.' : 'No devices match the current filters.'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <Modal title="Register Device" onClose={() => setShowCreate(false)}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Site</label>
              <select
                value={form.site_id}
                onChange={(e) => handleSiteChange(e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">License</label>
              <select
                value={form.license_id}
                onChange={(e) => setForm({ ...form, license_id: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                {sitesLicenses(form.site_id).length === 0 && <option value="">No licenses for this site</option>}
                {sitesLicenses(form.site_id).map((l) => (
                  <option key={l.id} value={l.id}>{l.plan_name} ({l.status})</option>
                ))}
              </select>
              <p className="text-xs text-[var(--zr-faint)] mt-1">
                POS login is rejected unless this license is active.
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Device Name</label>
              <input
                value={form.device_name}
                onChange={(e) => setForm({ ...form, device_name: e.target.value })}
                required
                placeholder="Front Counter Terminal"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Device Token</label>
              <div className="flex gap-2">
                <input
                  value={form.device_token}
                  onChange={(e) => setForm({ ...form, device_token: e.target.value })}
                  required
                  minLength={8}
                  className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
                <button
                  type="button"
                  onClick={() => setForm({ ...form, device_token: generateToken() })}
                  className="zr-action text-xs whitespace-nowrap"
                >
                  Generate
                </button>
              </div>
              <p className="text-xs text-[var(--zr-faint)] mt-1">
                Enter this into the app's Device Setup screen on the terminal being paired.
              </p>
            </div>
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800">Cancel</button>
              <button
                type="submit"
                disabled={createMutation.isPending || !form.license_id}
                className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg"
              >
                Register
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
