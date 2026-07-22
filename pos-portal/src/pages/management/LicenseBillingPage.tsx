/**
 * Management-portal License & Billing page — brand/site-scoped, read-only
 * view of licenses with an editable seat capacity.
 *
 * Mirrors DevicesPage.tsx's brand/site scoping. Commercial terms (plan,
 * monthly fee, expiry) and status transitions (disable/enable) stay
 * SuperAdmin-only via the admin-portal LicensesPage — this page only
 * exposes /licenses/management's restricted PATCH (max_devices).
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, fetchAll } from '../../api/axios'
import { useAuth, isMgmtUser } from '../../context/AuthContext'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { StatusBadge } from '../../components/StatusBadge'
import type { License, PosDevice, Site } from '../../types'

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

export function LicenseBillingPage() {
  const qc = useQueryClient()
  const { user } = useAuth()
  const brandId = useMgmtBrandId()
  const mgmtUser = isMgmtUser(user) ? user : null
  const fixedSiteId = mgmtUser?.site_id ?? null

  const [selectedSiteId, setSelectedSiteId] = useState('')
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
    data: licenses = [],
    isLoading,
    error,
  } = useQuery<License[]>({
    queryKey: ['management-licenses', queryParams],
    queryFn: () => fetchAll<License>('/licenses/management', queryParams),
    enabled: !!brandId || !!fixedSiteId,
  })

  const { data: devices = [] } = useQuery<PosDevice[]>({
    queryKey: ['management-devices-for-licenses', queryParams],
    queryFn: () => fetchAll<PosDevice>('/pos-devices/management', queryParams),
    enabled: !!brandId || !!fixedSiteId,
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['management-licenses'] })

  const [editingSeatsId, setEditingSeatsId] = useState<string | null>(null)
  const [seatsDraft, setSeatsDraft] = useState('')

  const updateSeatsMutation = useMutation({
    mutationFn: ({ id, max_devices }: { id: string; max_devices: number }) =>
      api.patch(`/licenses/management/${id}`, { max_devices }),
    onSuccess: () => {
      invalidate()
      setActionError(null)
      setEditingSeatsId(null)
    },
    onError: (e: unknown) => {
      invalidate()
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setActionError(msg ?? 'Failed to update seat capacity.')
    },
  })

  const siteName = (id: string) => sites.find((s) => s.id === id)?.name ?? id.slice(0, 8)

  const activeDeviceCount = (licenseId: string) =>
    devices.filter((d) => d.license_id === licenseId && d.is_active).length

  const startEditSeats = (l: License) => {
    setEditingSeatsId(l.id)
    setSeatsDraft(String(l.max_devices))
  }

  const commitEditSeats = (id: string) => {
    const parsed = parseInt(seatsDraft, 10)
    if (Number.isFinite(parsed) && parsed >= 1) {
      updateSeatsMutation.mutate({ id, max_devices: parsed })
    } else {
      setEditingSeatsId(null)
    }
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
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">License &amp; Billing</h1>
      </div>

      {actionError && <p className="text-sm text-red-600">{actionError}</p>}

      {needsSiteSelector && (
        <div className="flex flex-wrap items-end gap-3">
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
        </div>
      )}

      {isLoading ? (
        <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
      ) : error ? (
        <p className="text-sm text-red-500">Failed to load licenses.</p>
      ) : (
        <div className="zr-table-wrap">
          <table className="zr-table min-w-[640px]">
            <thead>
              <tr>
                {!fixedSiteId && <th>Site</th>}
                <th>Plan</th>
                <th className="zr-num">Monthly Fee</th>
                <th>Expires</th>
                <th>Seats</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {licenses.map((l) => (
                <tr key={l.id}>
                  {!fixedSiteId && <td className="text-[var(--zr-muted)]">{siteName(l.site_id)}</td>}
                  <td className="font-medium">
                    {l.plan_name}
                    {l.is_trial && <span className="ml-1 text-xs text-brand-500">(trial)</span>}
                  </td>
                  <td className="zr-num font-mono">{formatCents(l.monthly_fee_cents)}</td>
                  <td className="text-[var(--zr-muted)]">{new Date(l.expires_at).toLocaleDateString()}</td>
                  <td className="zr-cell-pad">
                    {editingSeatsId === l.id ? (
                      <input
                        type="number"
                        min={1}
                        autoFocus
                        value={seatsDraft}
                        onChange={(e) => setSeatsDraft(e.target.value)}
                        onBlur={() => commitEditSeats(l.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') commitEditSeats(l.id)
                          if (e.key === 'Escape') setEditingSeatsId(null)
                        }}
                        className="w-16 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-sm font-mono focus:outline-none focus:ring-2 focus:ring-brand-500"
                      />
                    ) : (
                      <button
                        onClick={() => startEditSeats(l)}
                        title="Click to change seat capacity"
                        className="font-mono text-sm hover:underline"
                      >
                        {activeDeviceCount(l.id)} of {l.max_devices}
                      </button>
                    )}
                  </td>
                  <td><StatusBadge status={l.status} /></td>
                </tr>
              ))}
              {licenses.length === 0 && (
                <tr>
                  <td colSpan={fixedSiteId ? 4 : 5} className="text-center text-[var(--zr-faint)] py-8">
                    No licenses yet.
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
