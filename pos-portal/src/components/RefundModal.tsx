/**
 * Refund flow for one paid invoice — full refund, or partial by line item
 * (checkbox selection). Posts to POST /invoice-reports/{id}/refund, the
 * portal-initiated equivalent of the POS terminal's own transactional
 * refund route (routes/invoices.py) — see that route's docstring for why a
 * portal refund carries no register_session_id.
 *
 * Only a PAID, not-yet-refunded invoice can be refunded — callers gate the
 * "Refund" row action on that before rendering this modal at all.
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/axios'
import { apiErrorMessage } from '../utils/apiError'
import { Modal } from './Modal'
import type { InvoiceDetail } from '../types'

function centsToDisplay(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

interface Props {
  invoiceId: string
  brandId: string | null
  onClose: () => void
}

export function RefundModal({ invoiceId, brandId, onClose }: Props) {
  const queryClient = useQueryClient()
  const params = brandId ? { brand_id: brandId } : {}

  const { data: invoice, isLoading, error } = useQuery<InvoiceDetail>({
    queryKey: ['invoice-report-detail', invoiceId, brandId],
    queryFn: () => api.get(`/invoice-reports/${invoiceId}`, { params }).then((r) => r.data),
  })

  const [mode, setMode] = useState<'full' | 'partial'>('full')
  const [selectedLineIds, setSelectedLineIds] = useState<Set<string>>(new Set())
  const [reason, setReason] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const toggleLine = (id: string) => {
    setSelectedLineIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const partialRefundCents = invoice
    ? invoice.line_items
        .filter((li) => selectedLineIds.has(li.id))
        .reduce((sum, li) => sum + li.line_total_cents + li.modifiers.reduce((m, mo) => m + mo.price_delta_cents, 0), 0)
    : 0

  const refundMutation = useMutation({
    mutationFn: () =>
      api.post(
        `/invoice-reports/${invoiceId}/refund`,
        {
          reason: reason.trim() || null,
          line_item_ids: mode === 'partial' ? Array.from(selectedLineIds) : null,
        },
        { params },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoice-reports'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-report-detail', invoiceId, brandId] })
      onClose()
    },
    onError: (e: unknown) => {
      queryClient.invalidateQueries({ queryKey: ['invoice-reports'] })
      setFormError(apiErrorMessage(e, 'Failed to process refund.'))
    },
  })

  const canSubmit = mode === 'full' || selectedLineIds.size > 0

  return (
    <Modal title="Refund invoice" onClose={onClose}>
      {isLoading ? (
        <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
      ) : error || !invoice ? (
        <p className="text-sm text-red-500">Failed to load invoice.</p>
      ) : (
        <div className="space-y-4">
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setMode('full')}
              className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium border ${
                mode === 'full'
                  ? 'bg-brand-600 border-brand-600 text-white'
                  : 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300'
              }`}
            >
              Full refund ({centsToDisplay(invoice.total_cents)})
            </button>
            <button
              type="button"
              onClick={() => setMode('partial')}
              className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium border ${
                mode === 'partial'
                  ? 'bg-brand-600 border-brand-600 text-white'
                  : 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300'
              }`}
            >
              Partial (by item)
            </button>
          </div>

          {mode === 'partial' && (
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg divide-y divide-gray-100 dark:divide-gray-700 max-h-64 overflow-y-auto">
              {invoice.line_items.map((li) => {
                const lineTotal = li.line_total_cents + li.modifiers.reduce((m, mo) => m + mo.price_delta_cents, 0)
                return (
                  <label key={li.id} className="flex items-center gap-3 px-3 py-2 cursor-pointer">
                    <input
                      type="checkbox"
                      className="zr-chk"
                      checked={selectedLineIds.has(li.id)}
                      onChange={() => toggleLine(li.id)}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-900 dark:text-gray-100 truncate">
                        {li.quantity}× {li.product_name}
                      </p>
                      {li.modifiers.map((mo) => (
                        <p key={mo.id} className="text-xs text-gray-400 dark:text-gray-500">· {mo.modifier_name}</p>
                      ))}
                    </div>
                    <span className="text-sm font-mono text-gray-700 dark:text-gray-300">{centsToDisplay(lineTotal)}</span>
                  </label>
                )
              })}
              {invoice.line_items.length === 0 && (
                <p className="text-sm text-gray-400 dark:text-gray-500 px-3 py-4 text-center">No line items on this invoice.</p>
              )}
            </div>
          )}

          {mode === 'partial' && (
            <p className="text-sm text-gray-600 dark:text-gray-300">
              Refund amount: <span className="font-medium">{centsToDisplay(partialRefundCents)}</span>
            </p>
          )}

          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Reason (optional)</label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              placeholder="e.g. Customer changed order"
            />
          </div>

          {formError && <p className="text-sm text-red-500">{formError}</p>}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!canSubmit || refundMutation.isPending}
              onClick={() => { setFormError(null); refundMutation.mutate() }}
              className="bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              {refundMutation.isPending ? 'Refunding…' : 'Confirm refund'}
            </button>
          </div>
        </div>
      )}
    </Modal>
  )
}
