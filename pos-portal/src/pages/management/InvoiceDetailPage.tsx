/**
 * Invoice detail page (Stage 21) — line items, tax breakdown, payments,
 * PDF export, and a change-log panel sourced from audit_logs.
 */

import { Fragment, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { StatusBadge } from '../../components/StatusBadge'
import { EntityIdChip } from '../../components/EntityIdChip'
import { downloadBlob } from '../../utils/download'
import type { InvoiceChangeLogEntry, InvoiceDetail } from '../../types'

function centsToDisplay(cents: number): string {
  const sign = cents < 0 ? '-' : ''
  return `${sign}$${(Math.abs(cents) / 100).toFixed(2)}`
}

const ACTION_LABELS: Record<string, string> = {
  'invoice.created': 'Invoice created',
  'invoice.discount.applied': 'Discount applied',
  'invoice.paid': 'Payment recorded',
  'invoice.voided': 'Invoice voided',
  'invoice.refunded': 'Refunded',
}

export function InvoiceDetailPage() {
  const { invoiceId } = useParams<{ invoiceId: string }>()
  const brandId = useMgmtBrandId()
  const [isDownloading, setIsDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  const params = brandId ? { brand_id: brandId } : {}

  const { data: invoice, isLoading, error } = useQuery<InvoiceDetail>({
    queryKey: ['invoice-report-detail', invoiceId, brandId],
    queryFn: () => api.get(`/invoice-reports/${invoiceId}`, { params }).then((r) => r.data),
    enabled: !!invoiceId,
  })

  const { data: changeLog = [] } = useQuery<InvoiceChangeLogEntry[]>({
    queryKey: ['invoice-report-change-log', invoiceId, brandId],
    queryFn: () => api.get(`/invoice-reports/${invoiceId}/change-log`, { params }).then((r) => r.data),
    enabled: !!invoiceId,
  })

  const handleDownloadPdf = async () => {
    setDownloadError(null)
    setIsDownloading(true)
    try {
      const resp = await api.get(`/invoice-reports/${invoiceId}/pdf`, { params, responseType: 'blob' })
      downloadBlob(resp.data, `invoice_${invoiceId}.pdf`)
    } catch {
      setDownloadError('Failed to download PDF.')
    } finally {
      setIsDownloading(false)
    }
  }

  if (isLoading) return <div className="p-4 sm:p-6 text-sm text-gray-400">Loading…</div>
  if (error || !invoice) return <div className="p-4 sm:p-6 text-sm text-red-500">Failed to load invoice.</div>

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link
            to={`/management/invoices${brandId ? `?brand_id=${brandId}` : ''}`}
            className="text-xs text-brand-600 hover:underline"
          >
            &larr; Back to invoices
          </Link>
          <div className="flex items-center gap-2 mt-1">
            <h1 className="text-xl font-semibold text-gray-900">Invoice</h1>
            <EntityIdChip id={invoice.id} />
            <StatusBadge status={invoice.status} />
            {invoice.is_refunded && (
              <span className="text-xs text-amber-600 font-medium">Refunded</span>
            )}
          </div>
          <p className="text-sm text-gray-500 mt-1">
            {invoice.brand_name} · {invoice.site_name} · {new Date(invoice.created_at).toLocaleString()}
          </p>
        </div>
        <button
          onClick={handleDownloadPdf}
          disabled={isDownloading}
          className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          {isDownloading ? 'Preparing…' : 'Download PDF'}
        </button>
      </div>
      {downloadError && <p className="text-sm text-red-500">{downloadError}</p>}

      {/* Line items */}
      <div className="overflow-x-auto rounded-xl border border-gray-200">
        <table className="w-full text-sm min-w-[560px]">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Item</th>
              <th className="text-right px-4 py-3 font-medium text-gray-600">Qty</th>
              <th className="text-right px-4 py-3 font-medium text-gray-600">Price</th>
              <th className="text-right px-4 py-3 font-medium text-gray-600">Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {invoice.line_items.map((item) => (
              <Fragment key={item.id}>
                <tr className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-gray-900">{item.product_name}</td>
                  <td className="px-4 py-3 text-right text-gray-700">{item.quantity}</td>
                  <td className="px-4 py-3 text-right text-gray-700">{centsToDisplay(item.unit_price_cents)}</td>
                  <td className="px-4 py-3 text-right font-medium text-gray-900">{centsToDisplay(item.line_total_cents)}</td>
                </tr>
                {item.modifiers.map((mod) => (
                  <tr key={mod.id} className="text-gray-400 text-xs">
                    <td className="px-4 py-1 pl-8">+ {mod.modifier_name}</td>
                    <td></td>
                    <td></td>
                    <td className="px-4 py-1 text-right">{centsToDisplay(mod.price_delta_cents)}</td>
                  </tr>
                ))}
              </Fragment>
            ))}
            {invoice.line_items.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-gray-400">No line items.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="grid sm:grid-cols-2 gap-6">
        {/* Tax breakdown */}
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Tax breakdown</h2>
          <div className="overflow-x-auto rounded-xl border border-gray-200">
            <table className="w-full text-sm min-w-[300px]">
              <tbody className="divide-y divide-gray-100">
                {invoice.tax_breakdown.map((t) => (
                  <tr key={t.id}>
                    <td className="px-4 py-2 text-gray-700">{t.tax_rate_name} ({t.rate_percent}%)</td>
                    <td className="px-4 py-2 text-right text-gray-900">{centsToDisplay(t.tax_amount_cents)}</td>
                  </tr>
                ))}
                {invoice.tax_breakdown.length === 0 && (
                  <tr><td className="px-4 py-4 text-center text-gray-400">No tax applied.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Payments */}
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Payments</h2>
          <div className="overflow-x-auto rounded-xl border border-gray-200">
            <table className="w-full text-sm min-w-[300px]">
              <tbody className="divide-y divide-gray-100">
                {invoice.payments.map((p) => (
                  <tr key={p.id}>
                    <td className="px-4 py-2 text-gray-700 capitalize">{p.method}</td>
                    <td className="px-4 py-2 text-gray-400 text-xs">{p.reference ?? ''}</td>
                    <td className="px-4 py-2 text-right text-gray-900">{centsToDisplay(p.amount_cents)}</td>
                  </tr>
                ))}
                {invoice.payments.length === 0 && (
                  <tr><td className="px-4 py-4 text-center text-gray-400">No payments recorded.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Totals */}
      <div className="w-full sm:w-64 sm:ml-auto space-y-1 text-sm">
        <div className="flex justify-between"><span className="text-gray-500">Subtotal</span><span className="text-gray-900">{centsToDisplay(invoice.subtotal_cents)}</span></div>
        <div className="flex justify-between"><span className="text-gray-500">Tax</span><span className="text-gray-900">{centsToDisplay(invoice.tax_cents)}</span></div>
        {invoice.discount_cents > 0 && (
          <div className="flex justify-between">
            <span className="text-gray-500">Discount{invoice.discount_reason ? ` (${invoice.discount_reason})` : ''}</span>
            <span className="text-gray-900">-{centsToDisplay(invoice.discount_cents)}</span>
          </div>
        )}
        <div className="flex justify-between font-semibold border-t border-gray-200 pt-1"><span>Total</span><span>{centsToDisplay(invoice.total_cents)}</span></div>
      </div>

      {/* Change log */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 mb-2">Change log</h2>
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm min-w-[560px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">When</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Action</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">By</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {changeLog.map((entry) => (
                <tr key={entry.id}>
                  <td className="px-4 py-3 text-gray-700 whitespace-nowrap">{new Date(entry.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-gray-900">{ACTION_LABELS[entry.action] ?? entry.action}</td>
                  <td className="px-4 py-3 text-gray-700">{entry.actor_name ?? entry.actor_email ?? (entry.actor_type === 'system' ? 'System' : 'Unknown')}</td>
                </tr>
              ))}
              {changeLog.length === 0 && (
                <tr><td colSpan={3} className="px-4 py-8 text-center text-gray-400">No changes recorded.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
