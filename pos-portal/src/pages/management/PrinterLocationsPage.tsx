/** Printer Locations tab (Printing section) — simple CRUD list.
 *
 * Each location auto-creates its own Order Docket print template on the
 * backend (see printer_location_service.create_printer_location) — no
 * separate "create template" step. copy_count controls how many times the
 * order docket prints for this location on the POS.
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, fetchAll } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { EditableText } from '../../components/EditableCell'
import { StatusBadge } from '../../components/StatusBadge'
import { apiErrorMessage } from '../../utils/apiError'
import type { PrinterLocation } from '../../types'

export function PrinterLocationsPage() {
  const qc = useQueryClient()
  const brandId = useMgmtBrandId()
  const params = brandId ? { brand_id: brandId } : {}

  const [adding, setAdding] = useState(false)
  const [draftName, setDraftName] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const { data: locations = [], isLoading } = useQuery<PrinterLocation[]>({
    queryKey: ['printer-locations', brandId],
    queryFn: () => fetchAll<PrinterLocation>('/printer-locations', { ...params, include_inactive: true }),
    enabled: brandId !== undefined,
  })

  const invalidateList = () => qc.invalidateQueries({ queryKey: ['printer-locations', brandId] })

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.patch(`/printer-locations/${id}`, body, { params }),
    onSuccess: invalidateList,
    onError: invalidateList,
  })

  const create = useMutation({
    mutationFn: (name: string) => api.post('/printer-locations', { name }, { params }),
    onSuccess: (resp) => {
      qc.setQueryData<PrinterLocation[]>(['printer-locations', brandId], (old) => (old ? [...old, resp.data] : old))
      invalidateList()
      setAdding(false)
      setDraftName('')
      setFormError(null)
    },
    onError: (e: unknown) => { invalidateList(); setFormError(apiErrorMessage(e, 'Failed to create printer location.')) },
  })

  if (!brandId) {
    return <div className="flex items-center justify-center h-64 text-sm text-gray-400">No brand context available.</div>
  }

  return (
    <div className="p-4 sm:p-6" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      <div className="max-w-3xl mx-auto">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Printer Locations</h1>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Items sharing a printer location print together as one order docket. Assign products to a
              location from the Products table.
            </p>
          </div>
          <button
            onClick={() => { setAdding(true); setDraftName(''); setFormError(null) }}
            className="px-3 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors flex-none"
          >
            + Printer location
          </button>
        </div>

        {adding && (
          <div className="flex flex-wrap items-center gap-3 bg-white dark:bg-gray-800 border border-brand-400 dark:border-brand-600 rounded-lg px-4 py-3 mb-4">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-brand-600 whitespace-nowrap">
              New printer location
            </span>
            <input
              autoFocus
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              placeholder="e.g. Kitchen, Bar"
              className="flex-1 min-w-[140px] px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
            <div className="flex-1" />
            {formError && <p className="text-xs text-red-600">{formError}</p>}
            <button onClick={() => setAdding(false)} className="text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700">
              Cancel
            </button>
            <button
              onClick={() => { if (draftName) create.mutate(draftName) }}
              disabled={create.isPending}
              className="px-3.5 py-2 bg-brand-600 text-white text-xs font-semibold rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors whitespace-nowrap"
            >
              {create.isPending ? 'Adding…' : 'Add location'}
            </button>
          </div>
        )}

        {isLoading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : locations.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-8">No printer locations yet.</p>
        ) : (
          <div className="zr-table-wrap">
            <table className="zr-table min-w-[520px]">
              <thead>
                <tr>
                  <th>Name</th>
                  <th className="zr-num">Copies</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {locations.map((loc) => (
                  <tr key={loc.id}>
                    <td className="font-medium zr-cell-pad">
                      <EditableText
                        value={loc.name}
                        onSave={async (v) => { await patch.mutateAsync({ id: loc.id, body: { name: v } }) }}
                      />
                    </td>
                    <td className="zr-num zr-cell-pad">
                      <EditableText
                        type="number"
                        value={String(loc.copy_count)}
                        onSave={async (v) => {
                          const n = Math.max(1, parseInt(v, 10) || 1)
                          await patch.mutateAsync({ id: loc.id, body: { copy_count: n } })
                        }}
                      />
                    </td>
                    <td>
                      <StatusBadge
                        status={loc.is_active ? 'active' : 'inactive'}
                        onClick={() => patch.mutate({ id: loc.id, body: { is_active: !loc.is_active } })}
                        title={loc.is_active ? 'Click to deactivate' : 'Click to reactivate'}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
