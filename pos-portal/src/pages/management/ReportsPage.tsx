/**
 * Reports page — daily sales for the management user's scope.
 *
 * Site-scope management users: site_id comes from JWT automatically.
 * Brand/group-scope management users: pick a site from the brand's list.
 * SuperAdmins: must supply brand_id via URL param and pick a site.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useAuth, isMgmtUser } from '../../context/AuthContext'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import type { Site } from '../../types'

interface DailySalesRow {
  brand_id: string
  site_id: string
  sale_date: string
  invoice_count: number
  subtotal_cents: number
  tax_cents: number
  discount_cents: number
  total_cents: number
}

function centsToDisplay(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

function todayStr(): string {
  return new Date().toISOString().slice(0, 10)
}

function thirtyDaysAgo(): string {
  const d = new Date()
  d.setDate(d.getDate() - 30)
  return d.toISOString().slice(0, 10)
}

export function ReportsPage() {
  const { user } = useAuth()
  const brandId = useMgmtBrandId()
  const [startDate, setStartDate] = useState(thirtyDaysAgo())
  const [endDate, setEndDate] = useState(todayStr())
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null)

  const mgmtUser = isMgmtUser(user) ? user : null

  // Site-scope management users have site_id in JWT — no selector needed
  const fixedSiteId = mgmtUser?.site_id ?? null
  const siteId = fixedSiteId ?? selectedSiteId

  // Fetch sites list for the brand (only when brand-scope or SuperAdmin needs to pick)
  const needsSiteSelector = !fixedSiteId && !!brandId
  const { data: sites = [] } = useQuery<Site[]>({
    queryKey: ['sites-for-brand', brandId],
    queryFn: () => api.get('/sites', { params: { brand_id: brandId } }).then((r) => r.data),
    enabled: needsSiteSelector,
  })

  const queryParams: Record<string, string> = {
    site_id: siteId ?? '',
    start_date: startDate,
    end_date: endDate,
  }
  if (brandId) queryParams.brand_id = brandId

  const { data: rows = [], isLoading, error } = useQuery<DailySalesRow[]>({
    queryKey: ['reports-daily', siteId, startDate, endDate, brandId],
    queryFn: () => api.get('/reports/daily-sales', { params: queryParams }).then((r) => r.data),
    enabled: !!siteId,
  })

  const totalRevenue = rows.reduce((sum, r) => sum + r.total_cents, 0)
  const totalInvoices = rows.reduce((sum, r) => sum + r.invoice_count, 0)

  if (!brandId && !fixedSiteId) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-gray-400 dark:text-gray-500">
        No brand or site context available.
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 space-y-6">
      {/* Controls */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Daily Sales Report</h1>
        <div className="flex items-end gap-3 flex-wrap">
          {needsSiteSelector && sites.length > 0 && (
            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Site</label>
              <select
                value={selectedSiteId ?? ''}
                onChange={(e) => setSelectedSiteId(e.target.value || null)}
                className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="">Select site…</option>
                {sites.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
          )}
          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">From</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">To</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
        </div>
      </div>

      {!siteId ? (
        <div className="flex items-center justify-center h-40 text-sm text-gray-400 dark:text-gray-500">
          Select a site to view report data.
        </div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">Total revenue</p>
              <p className="text-2xl font-semibold text-gray-900 dark:text-gray-100 mt-1">{centsToDisplay(totalRevenue)}</p>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">Total invoices</p>
              <p className="text-2xl font-semibold text-gray-900 dark:text-gray-100 mt-1">{totalInvoices}</p>
            </div>
          </div>

          {/* Table */}
          {isLoading ? (
            <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
          ) : error ? (
            <p className="text-sm text-red-500">Failed to load report data.</p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700">
              <table className="w-full text-sm min-w-[480px]">
                <thead className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-400">Date</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-600 dark:text-gray-400">Invoices</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-600 dark:text-gray-400">Subtotal</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-600 dark:text-gray-400">Tax</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-600 dark:text-gray-400">Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {rows.map((r, i) => (
                    <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-800/60">
                      <td className="px-4 py-3 text-gray-900 dark:text-gray-100">{r.sale_date}</td>
                      <td className="px-4 py-3 text-right text-gray-700 dark:text-gray-300">{r.invoice_count}</td>
                      <td className="px-4 py-3 text-right text-gray-700 dark:text-gray-300">{centsToDisplay(r.subtotal_cents)}</td>
                      <td className="px-4 py-3 text-right text-gray-700 dark:text-gray-300">{centsToDisplay(r.tax_cents)}</td>
                      <td className="px-4 py-3 text-right font-medium text-gray-900 dark:text-gray-100">{centsToDisplay(r.total_cents)}</td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-center text-gray-400 dark:text-gray-500">
                        No sales data for the selected period.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
