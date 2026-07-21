/**
 * Register (till) session reporting page — Android POS Phase 1's remaining
 * portal item. Backend route (`GET /register-session-reports`) already
 * existed; this is the first UI surface for it.
 *
 * Session volume is small (one row per device per shift, per
 * register_session_report_service.py's docstring) so — unlike Invoices,
 * which is unbounded and uses true server-side pagination — this page
 * follows the catalog-page convention: fetchAll the brand/site's full list,
 * then filter client-side with no extra requests.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchAll } from '../../api/axios'
import { useAuth, isMgmtUser } from '../../context/AuthContext'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { StatusBadge } from '../../components/StatusBadge'
import { EntityIdChip } from '../../components/EntityIdChip'
import type { RegisterSessionReportRow, Site } from '../../types'

function centsToDisplay(cents: number | null): string {
  if (cents === null) return '—'
  return `$${(cents / 100).toFixed(2)}`
}

function varianceClass(cents: number | null): string {
  if (cents === null) return 'text-gray-400 dark:text-gray-500'
  return cents === 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
}

export function RegisterSessionsPage() {
  const { user } = useAuth()
  const brandId = useMgmtBrandId()
  const mgmtUser = isMgmtUser(user) ? user : null
  const fixedSiteId = mgmtUser?.site_id ?? null

  const [selectedSiteId, setSelectedSiteId] = useState<string>('')
  const [statusFilter, setStatusFilter] = useState('')
  const [deviceFilter, setDeviceFilter] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

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

  const { data: sessions = [], isLoading, error } = useQuery<RegisterSessionReportRow[]>({
    queryKey: ['register-session-reports', queryParams],
    queryFn: () => fetchAll<RegisterSessionReportRow>('/register-session-reports', queryParams),
    enabled: !!brandId || !!fixedSiteId,
  })

  // Device options are derived from the loaded rows — /pos-devices is
  // portal-admin-only, so there's no brand/site-scoped device list to fetch.
  const devices = Array.from(
    new Map(sessions.map((s) => [s.device_id, s.device_name])).entries(),
  ).sort((a, b) => a[1].localeCompare(b[1]))

  const filtered = sessions.filter((s) => {
    if (statusFilter && s.status !== statusFilter) return false
    if (deviceFilter && s.device_id !== deviceFilter) return false
    if (startDate && s.opened_at.slice(0, 10) < startDate) return false
    if (endDate && s.opened_at.slice(0, 10) > endDate) return false
    return true
  })

  const hasFilters = !!(statusFilter || deviceFilter || startDate || endDate || selectedSiteId)
  const clearFilters = () => {
    setStatusFilter('')
    setDeviceFilter('')
    setStartDate('')
    setEndDate('')
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
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Register Sessions</h1>
      </div>

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
            <option value="open">Open</option>
            <option value="closed">Closed</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Terminal</label>
          <select
            value={deviceFilter}
            onChange={(e) => setDeviceFilter(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="">Any</option>
            {devices.map(([id, name]) => (
              <option key={id} value={id}>{name}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">From</label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">To</label>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        {hasFilters && (
          <button onClick={clearFilters} className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 pb-2">
            Clear filters
          </button>
        )}
        <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto pb-2">
          {filtered.length} of {sessions.length}
        </span>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
      ) : error ? (
        <p className="text-sm text-red-500">Failed to load register sessions.</p>
      ) : (
        <div className="zr-table-wrap">
          <table className="zr-table min-w-[960px]">
            <thead>
              <tr>
                <th>Session</th>
                <th>Terminal</th>
                {!fixedSiteId && <th>Site</th>}
                <th>Status</th>
                <th>Opened</th>
                <th>Opened by</th>
                <th className="zr-num">Opening cash</th>
                <th>Closed</th>
                <th>Closed by</th>
                <th className="zr-num">Closing cash</th>
                <th className="zr-num">Takings</th>
                <th className="zr-num">Variance</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <tr key={s.id}>
                  <td className="px-4 py-3"><EntityIdChip id={s.id} /></td>
                  <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{s.device_name}</td>
                  {!fixedSiteId && <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{s.site_name}</td>}
                  <td className="px-4 py-3"><StatusBadge status={s.status} /></td>
                  <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{new Date(s.opened_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{s.opened_by_name}</td>
                  <td className="zr-num px-4 py-3">{centsToDisplay(s.opening_cash_cents)}</td>
                  <td className="px-4 py-3 text-gray-700 dark:text-gray-300">
                    {s.closed_at ? new Date(s.closed_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{s.closed_by_name ?? '—'}</td>
                  <td className="zr-num px-4 py-3">{centsToDisplay(s.closing_cash_cents)}</td>
                  <td className="zr-num px-4 py-3">{centsToDisplay(s.cash_takings_cents)}</td>
                  <td className={`zr-num px-4 py-3 font-medium ${varianceClass(s.variance_cents)}`}>
                    {centsToDisplay(s.variance_cents)}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={fixedSiteId ? 11 : 12} className="px-4 py-8 text-center text-gray-400 dark:text-gray-500">
                    No register sessions yet.
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
