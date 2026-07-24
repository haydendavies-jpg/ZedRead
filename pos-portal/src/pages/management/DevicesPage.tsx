/**
 * Management-portal Devices page — brand/site-scoped view of self-claimed
 * POS terminals, with a Release action to free a license seat.
 *
 * Terminals claim their own seat by logging in (see the auth rework); this
 * page is where a manager frees one back up — e.g. a terminal was
 * decommissioned, or a seat needs handing to a different site — without
 * needing admin-portal access. Session volume mirrors Register Sessions
 * (small, one row per terminal), so this follows the same fetchAll +
 * client-side-filter pattern rather than true server pagination.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, fetchAll } from '../../api/axios'
import { useAuth, isMgmtUser } from '../../context/AuthContext'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { StatusBadge } from '../../components/StatusBadge'
import { EditableText } from '../../components/EditableCell'
import type { PosDevice, Site } from '../../types'

export function DevicesPage() {
  const qc = useQueryClient()
  const { user } = useAuth()
  const brandId = useMgmtBrandId()
  const mgmtUser = isMgmtUser(user) ? user : null
  const fixedSiteId = mgmtUser?.site_id ?? null

  const [selectedSiteId, setSelectedSiteId] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)

  const siteId = fixedSiteId ?? selectedSiteId

  const needsSiteSelector = !fixedSiteId && !!brandId
  const { data: sites = [] } = useQuery<Site[]>({
    queryKey: ['sites-for-brand', brandId],
    queryFn: () => fetchAll<Site>('/sites', { brand_id: brandId }),
    enabled: needsSiteSelector,
  })

  const queryParams: Record<string, string> = {}
  if (brandId) queryParams.brand_id = brandId
  if (siteId) queryParams.site_id = siteId

  const {
    data: devices = [],
    isLoading,
    error,
  } = useQuery<PosDevice[]>({
    queryKey: ['management-devices', queryParams],
    queryFn: () => fetchAll<PosDevice>('/pos-devices/management', queryParams),
    enabled: !!brandId || !!fixedSiteId,
  })

  const releaseMutation = useMutation({
    mutationFn: (id: string) => api.post(`/pos-devices/${id}/release`),
    onSuccess: () => {
      setActionError(null)
      qc.invalidateQueries({ queryKey: ['management-devices'] })
    },
    onError: (e: unknown) => {
      qc.invalidateQueries({ queryKey: ['management-devices'] })
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setActionError(msg ?? 'Failed to release device.')
    },
  })

  const renameMutation = useMutation({
    mutationFn: ({ id, device_name }: { id: string; device_name: string }) =>
      api.patch(`/pos-devices/${id}`, { device_name }),
    onSuccess: () => {
      setActionError(null)
      qc.invalidateQueries({ queryKey: ['management-devices'] })
    },
    onError: () => {
      // Re-fetch so any DB-written rename still appears even if response
      // serialization failed — same "invalidate on error too" rule as every
      // other write mutation in this portal.
      qc.invalidateQueries({ queryKey: ['management-devices'] })
    },
  })

  const siteName = (id: string) => sites.find((s) => s.id === id)?.name ?? id.slice(0, 8)

  const filtered = devices.filter((d) => {
    if (statusFilter === 'active' && !d.is_active) return false
    if (statusFilter === 'inactive' && d.is_active) return false
    return true
  })

  const hasFilters = !!(statusFilter || selectedSiteId)
  const clearFilters = () => {
    setStatusFilter('')
    setSelectedSiteId('')
  }

  if (!brandId && !fixedSiteId) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-gray-400 dark:text-gray-500">
        No brand or site context available.
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Devices</h1>
      </div>

      {actionError && <p className="text-sm text-red-600">{actionError}</p>}

      <div className="flex flex-wrap items-end gap-3">
        {needsSiteSelector && (
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Site</label>
            <select
              value={selectedSiteId}
              onChange={(e) => setSelectedSiteId(e.target.value)}
              className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="">All sites</option>
              {sites.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
        )}
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Status</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="">Any</option>
            <option value="active">Active</option>
            <option value="inactive">Released</option>
          </select>
        </div>
        {hasFilters && (
          <button onClick={clearFilters} className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 pb-2">
            Clear filters
          </button>
        )}
        <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto pb-2">
          {filtered.length} of {devices.length}
        </span>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
      ) : error ? (
        <p className="text-sm text-red-500">Failed to load devices.</p>
      ) : (
        <div className="zr-table-wrap">
          <table className="zr-table min-w-[640px]">
            <thead>
              <tr>
                <th>Device</th>
                {!fixedSiteId && <th>Site</th>}
                <th>Hardware ID</th>
                <th>Registered</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((d) => (
                <tr key={d.id}>
                  <td className="font-medium">
                    <EditableText
                      value={d.device_name}
                      onSave={async (v) => { await renameMutation.mutateAsync({ id: d.id, device_name: v }) }}
                    />
                  </td>
                  {!fixedSiteId && <td className="text-[var(--zr-muted)]">{siteName(d.site_id)}</td>}
                  <td className="font-mono text-xs text-[var(--zr-muted)]" title={d.hardware_id ?? undefined}>
                    {d.hardware_id ? `${d.hardware_id.slice(0, 12)}…` : '—'}
                  </td>
                  <td className="text-[var(--zr-muted)]">{new Date(d.registered_at).toLocaleDateString()}</td>
                  <td><StatusBadge status={d.is_active ? 'active' : 'inactive'} /></td>
                  <td className="zr-cell-pad">
                    {d.is_active ? (
                      <button
                        onClick={() => releaseMutation.mutate(d.id)}
                        disabled={releaseMutation.isPending}
                        className="text-red-600 hover:underline text-xs disabled:opacity-50"
                      >
                        Release
                      </button>
                    ) : (
                      <span className="text-xs text-[var(--zr-faint)]">Released</span>
                    )}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={fixedSiteId ? 5 : 6} className="text-center text-[var(--zr-faint)] py-8">
                    {devices.length === 0 ? 'No devices registered yet.' : 'No devices match the current filters.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
