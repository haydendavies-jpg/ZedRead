/**
 * Invoice reporting page (Stage 21) — filtered list with XLSX export.
 *
 * Site-scope management users: site_id comes from JWT automatically.
 * Brand/group-scope management users: optionally pick a site from the brand's list.
 * SuperAdmins: must supply brand_id via URL param, and may optionally pick a site.
 */

import { Fragment, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, fetchAll } from '../../api/axios'
import { useAuth, isMgmtUser } from '../../context/AuthContext'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { StatusBadge } from '../../components/StatusBadge'
import { EntityIdChip } from '../../components/EntityIdChip'
import { RefundModal } from '../../components/RefundModal'
import { downloadBlob } from '../../utils/download'
import type { InvoiceDetail, InvoiceReportRow, Site } from '../../types'

// Server-side page size — invoice volume grows without bound, so unlike the
// catalog pages (which fetchAll and filter client-side) this list is truly
// paginated: filters are applied by the backend and each page is one request.
const PAGE_SIZE = 50

function centsToDisplay(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

function dollarsToCents(value: string): number | undefined {
  if (!value) return undefined
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : undefined
}

export function InvoicesPage() {
  const { user } = useAuth()
  const brandId = useMgmtBrandId()
  const mgmtUser = isMgmtUser(user) ? user : null
  const fixedSiteId = mgmtUser?.site_id ?? null

  const [selectedSiteId, setSelectedSiteId] = useState<string>('')
  const [statusFilter, setStatusFilter] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [minAmount, setMinAmount] = useState('')
  const [maxAmount, setMaxAmount] = useState('')
  const [isExporting, setIsExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [refundInvoiceId, setRefundInvoiceId] = useState<string | null>(null)

  const siteId = fixedSiteId ?? selectedSiteId

  const needsSiteSelector = !fixedSiteId && !!brandId
  const { data: sites = [] } = useQuery<Site[]>({
    queryKey: ['sites-for-brand', brandId],
    queryFn: () => fetchAll<Site>('/sites', { brand_id: brandId }),
    enabled: needsSiteSelector,
  })

  const [page, setPage] = useState(0)

  const queryParams: Record<string, string | number> = {
    limit: PAGE_SIZE,
    skip: page * PAGE_SIZE,
  }
  if (brandId) queryParams.brand_id = brandId
  if (siteId) queryParams.site_id = siteId
  if (statusFilter) queryParams.status = statusFilter
  if (startDate) queryParams.start_date = startDate
  if (endDate) queryParams.end_date = endDate
  const minCents = dollarsToCents(minAmount)
  const maxCents = dollarsToCents(maxAmount)
  if (minCents !== undefined) queryParams.min_amount_cents = minCents
  if (maxCents !== undefined) queryParams.max_amount_cents = maxCents

  // Changing any filter must snap back to the first page — page 3 of the old
  // filter set is meaningless under the new one
  useEffect(() => {
    setPage(0)
  }, [siteId, statusFilter, startDate, endDate, minAmount, maxAmount])

  const { data: invoices = [], isLoading, error } = useQuery<InvoiceReportRow[]>({
    queryKey: ['invoice-reports', queryParams],
    queryFn: () => api.get('/invoice-reports', { params: queryParams }).then((r) => r.data),
    enabled: !!brandId || !!fixedSiteId,
    // Keep the previous page's rows visible while the next page loads,
    // instead of flashing the whole table back to "Loading…"
    placeholderData: (prev) => prev,
  })

  // A full page means there may be more; a short page is definitely the end
  const hasMore = invoices.length === PAGE_SIZE

  const handleExport = async () => {
    setExportError(null)
    setIsExporting(true)
    try {
      // Export always covers the full filtered set — strip the pagination params
      const { limit: _limit, skip: _skip, ...exportParams } = queryParams
      const resp = await api.get('/invoice-reports/export', {
        params: exportParams,
        responseType: 'blob',
      })
      downloadBlob(resp.data, 'invoices_export.xlsx')
    } catch {
      setExportError('Failed to export invoices.')
    } finally {
      setIsExporting(false)
    }
  }

  const hasFilters = !!(statusFilter || startDate || endDate || minAmount || maxAmount || selectedSiteId)
  const clearFilters = () => {
    setStatusFilter('')
    setStartDate('')
    setEndDate('')
    setMinAmount('')
    setMaxAmount('')
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
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Invoices</h1>
        <button
          onClick={handleExport}
          disabled={isExporting}
          className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          {isExporting ? 'Exporting…' : 'Export XLSX'}
        </button>
      </div>
      {exportError && <p className="text-sm text-red-500">{exportError}</p>}

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
            <option value="draft">Draft</option>
            <option value="open">Open</option>
            <option value="paid">Paid</option>
            <option value="voided">Voided</option>
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
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Min total</label>
          <input
            type="number"
            step="0.01"
            placeholder="0.00"
            value={minAmount}
            onChange={(e) => setMinAmount(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm w-24 focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Max total</label>
          <input
            type="number"
            step="0.01"
            placeholder="0.00"
            value={maxAmount}
            onChange={(e) => setMaxAmount(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm w-24 focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        {hasFilters && (
          <button onClick={clearFilters} className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 pb-2">
            Clear filters
          </button>
        )}
        <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto pb-2">
          {invoices.length === 0
            ? '0 invoices'
            : `Showing ${page * PAGE_SIZE + 1}–${page * PAGE_SIZE + invoices.length}`}
        </span>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
      ) : error ? (
        <p className="text-sm text-red-500">Failed to load invoices.</p>
      ) : (
        <div className="zr-table-wrap">
          <table className="zr-table min-w-[860px]">
            <thead>
              <tr>
                <th>Invoice #</th>
                <th>Date</th>
                <th>Site</th>
                <th>Type</th>
                <th>Status</th>
                <th>Payment</th>
                <th className="zr-num">Total</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((inv) => {
                const isExpanded = expandedId === inv.id
                return (
                  <Fragment key={inv.id}>
                    <tr
                      onClick={() => setExpandedId(isExpanded ? null : inv.id)}
                      className="cursor-pointer"
                    >
                      <td className="px-4 py-3"><EntityIdChip id={inv.id} /></td>
                      <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{new Date(inv.created_at).toLocaleString()}</td>
                      <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{inv.site_name}</td>
                      <td className="px-4 py-3 text-gray-700 dark:text-gray-300 capitalize">
                        {inv.invoice_type}
                        {inv.is_refunded && <span className="ml-1 text-xs text-amber-600">(refunded)</span>}
                      </td>
                      <td className="px-4 py-3"><StatusBadge status={inv.status} /></td>
                      <td className="px-4 py-3 text-gray-700 dark:text-gray-300 capitalize">
                        {inv.payment_methods.length > 0 ? inv.payment_methods.join(', ') : '—'}
                      </td>
                      <td className="px-4 py-3 text-right font-medium text-gray-900 dark:text-gray-100">{centsToDisplay(inv.total_cents)}</td>
                      <td className="px-4 py-3 text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                        {inv.status === 'paid' && !inv.is_refunded && (
                          <button
                            onClick={() => setRefundInvoiceId(inv.id)}
                            className="text-red-600 hover:underline text-xs mr-3"
                          >
                            Refund
                          </button>
                        )}
                        <Link
                          to={`/management/invoices/${inv.id}${brandId ? `?brand_id=${brandId}` : ''}`}
                          className="text-brand-600 hover:underline text-xs"
                        >
                          View
                        </Link>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr>
                        <td colSpan={8} className="px-4 py-3 bg-gray-50 dark:bg-gray-800/50">
                          <ExpandedLineItems invoiceId={inv.id} brandId={brandId} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
              {invoices.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-400 dark:text-gray-500">
                    No invoices yet.
                  </td>
                </tr>
              )}
            </tbody>
            {invoices.length > 0 && (
              <tfoot>
                <tr
                  className="sticky bottom-0 z-10 bg-white dark:bg-gray-800 border-t-2 border-gray-200 dark:border-gray-700 font-semibold"
                >
                  <td className="px-4 py-3 text-gray-700 dark:text-gray-300" colSpan={6}>
                    Page total ({invoices.length} invoice{invoices.length === 1 ? '' : 's'})
                  </td>
                  <td className="px-4 py-3 text-right text-gray-900 dark:text-gray-100">
                    {centsToDisplay(invoices.reduce((sum, inv) => sum + inv.total_cents, 0))}
                  </td>
                  <td></td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}

      {refundInvoiceId && (
        <RefundModal
          invoiceId={refundInvoiceId}
          brandId={brandId ?? null}
          onClose={() => setRefundInvoiceId(null)}
        />
      )}

      {/* Pagination — shown whenever there is anything to page between */}
      {(page > 0 || hasMore) && (
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="zr-action disabled:opacity-40 disabled:cursor-not-allowed"
          >
            ← Previous
          </button>
          <span className="text-xs text-gray-400 dark:text-gray-500">Page {page + 1}</span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={!hasMore}
            className="zr-action disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}

/** A row's expanded detail — the invoice's line items (with modifiers), fetched lazily once expanded. */
function ExpandedLineItems({ invoiceId, brandId }: { invoiceId: string; brandId: string | null }) {
  const params = brandId ? { brand_id: brandId } : {}
  const { data: invoice, isLoading, error } = useQuery<InvoiceDetail>({
    queryKey: ['invoice-report-detail', invoiceId, brandId],
    queryFn: () => api.get(`/invoice-reports/${invoiceId}`, { params }).then((r) => r.data),
  })

  if (isLoading) return <p className="text-sm text-gray-400 dark:text-gray-500">Loading items…</p>
  if (error || !invoice) return <p className="text-sm text-red-500">Failed to load line items.</p>
  if (invoice.line_items.length === 0) {
    return <p className="text-sm text-gray-400 dark:text-gray-500">No line items on this invoice.</p>
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-xs text-gray-500 dark:text-gray-400">
          <th className="text-left font-medium pb-1">Item</th>
          <th className="text-right font-medium pb-1">Qty</th>
          <th className="text-right font-medium pb-1">Unit</th>
          <th className="text-right font-medium pb-1">Total</th>
        </tr>
      </thead>
      <tbody>
        {invoice.line_items.map((li) => {
          const modifierTotal = li.modifiers.reduce((sum, m) => sum + m.price_delta_cents, 0)
          return (
            <tr key={li.id} className="border-t border-gray-100 dark:border-gray-700">
              <td className="py-1.5 text-gray-800 dark:text-gray-200">
                {li.product_name}
                {li.modifiers.map((m) => (
                  <div key={m.id} className="text-xs text-gray-400 dark:text-gray-500">· {m.modifier_name}</div>
                ))}
              </td>
              <td className="py-1.5 text-right text-gray-600 dark:text-gray-300">{li.quantity}</td>
              <td className="py-1.5 text-right font-mono text-gray-600 dark:text-gray-300">{centsToDisplay(li.unit_price_cents)}</td>
              <td className="py-1.5 text-right font-mono text-gray-800 dark:text-gray-200">
                {centsToDisplay(li.line_total_cents + modifierTotal)}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
