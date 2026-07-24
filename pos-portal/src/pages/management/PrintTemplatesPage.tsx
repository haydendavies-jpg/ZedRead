/** Printer Templates tab (Printing section) — Invoice/Register Summary/Cash-in Slip
 * singletons plus one Order Docket row per printer location; clicking a row
 * opens the reorderable field editor (PrintTemplateEditor.tsx).
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, fetchAll } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { PrintTemplateEditor } from '../../components/PrintTemplateEditor'
import { TEMPLATE_TYPE_LABELS } from '../../utils/printFields'
import type { PrintTemplate, PrintTemplateDetail, PrintTemplateType } from '../../types'

const SINGLETON_ORDER: PrintTemplateType[] = ['invoice', 'register_summary', 'cash_in_slip']

export function PrintTemplatesPage() {
  const brandId = useMgmtBrandId()
  const params = brandId ? { brand_id: brandId } : {}
  const [editingId, setEditingId] = useState<string | null>(null)

  const { data: templates = [], isLoading } = useQuery<PrintTemplate[]>({
    queryKey: ['print-templates', brandId],
    queryFn: () => fetchAll<PrintTemplate>('/print-templates', params),
    enabled: brandId !== undefined,
  })

  const { data: templateDetail } = useQuery<PrintTemplateDetail>({
    queryKey: ['print-template-detail', editingId, brandId],
    queryFn: async () => (await api.get(`/print-templates/${editingId}`, { params })).data,
    enabled: !!editingId,
  })

  if (!brandId) {
    return <div className="flex items-center justify-center h-64 text-sm text-gray-400">No brand context available.</div>
  }

  const singletons = SINGLETON_ORDER.map((type) => templates.find((t) => t.template_type === type)).filter(
    (t): t is PrintTemplate => !!t,
  )
  const dockets = templates.filter((t) => t.template_type === 'docket')

  const Row = ({ template }: { template: PrintTemplate }) => (
    <button
      onClick={() => setEditingId(template.id)}
      className="w-full flex items-center gap-3 px-4 py-3 border-b last:border-b-0 border-gray-100 dark:border-gray-700 text-left hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors"
    >
      <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{template.name}</div>
      <span className="ml-auto text-[11px] font-medium text-gray-400 dark:text-gray-500 border border-gray-200 dark:border-gray-600 rounded-md px-2 py-1">
        {TEMPLATE_TYPE_LABELS[template.template_type]}
      </span>
    </button>
  )

  return (
    <div className="p-4 sm:p-6" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      <div className="max-w-3xl mx-auto">
        <div className="mb-4">
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Printer Templates</h1>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Every order docket has its own template, created automatically with its printer location.
          </p>
        </div>

        {isLoading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : (
          <div className="space-y-4">
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700 bg-gray-50/60 dark:bg-gray-900/30">
                <span className="font-serif font-bold text-[15px] text-gray-900 dark:text-gray-100">Standard templates</span>
              </div>
              {singletons.map((t) => <Row key={t.id} template={t} />)}
            </div>

            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700 bg-gray-50/60 dark:bg-gray-900/30">
                <span className="font-serif font-bold text-[15px] text-gray-900 dark:text-gray-100">Order dockets</span>
              </div>
              {dockets.length === 0 ? (
                <div className="px-4 py-6 text-center text-xs text-gray-400 dark:text-gray-500">
                  No printer locations yet — add one on the Printer Locations tab.
                </div>
              ) : (
                dockets.map((t) => <Row key={t.id} template={t} />)
              )}
            </div>
          </div>
        )}
      </div>

      {editingId && templateDetail && (
        <PrintTemplateEditor template={templateDetail} brandId={brandId} onClose={() => setEditingId(null)} />
      )}
    </div>
  )
}
