/** Product categories management page — grouped by Reporting Group.
 *
 * Menu Studio redesign: categories are grouped into cards by their reporting
 * group (design_handoff_menu_studio/README.md "Categories tab"), each row
 * carrying a colour swatch (the POS button default colour for that
 * category), with a floating bulk-assign bar when 1+ rows are selected.
 * Inline "+ Category" / "+ Reporting group" forms replace the old create modal.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, fetchAll } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { ColorSwatchPicker } from '../../components/ColorSwatchPicker'
import { EditableText } from '../../components/EditableCell'
import { StatusBadge } from '../../components/StatusBadge'
import { apiErrorMessage } from '../../utils/apiError'
import { DEFAULT_CATEGORY_COLOR } from '../../utils/menuStudio'
import type { Category, ReportingGroup } from '../../types'

type AddMode = 'category' | 'group' | null

export function CategoriesPage() {
  const qc = useQueryClient()
  const brandId = useMgmtBrandId()

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [assignMenuOpen, setAssignMenuOpen] = useState(false)
  const [adding, setAdding] = useState<AddMode>(null)
  const [draftName, setDraftName] = useState('')
  const [draftGroupId, setDraftGroupId] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const params = brandId ? { brand_id: brandId } : {}

  const { data: categories = [], isLoading } = useQuery<Category[]>({
    queryKey: ['categories', brandId],
    queryFn: () => fetchAll<Category>('/categories', { ...params, include_inactive: true }),
    enabled: brandId !== undefined,
  })

  const { data: reportingGroups = [] } = useQuery<ReportingGroup[]>({
    queryKey: ['reporting-groups', brandId],
    queryFn: () => fetchAll<ReportingGroup>('/reporting-groups', params),
    enabled: !!brandId,
  })

  const invalidateList = () => qc.invalidateQueries({ queryKey: ['categories', brandId] })
  const invalidateGroups = () => qc.invalidateQueries({ queryKey: ['reporting-groups', brandId] })

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.patch(`/categories/${id}`, body, { params }),
    onSuccess: invalidateList,
    onError: invalidateList,
  })

  const patchGroup = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.patch(`/reporting-groups/${id}`, body, { params }),
    onSuccess: invalidateGroups,
    onError: invalidateGroups,
  })

  const createCategory = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post('/categories', body, { params }),
    // Append the created row to the cache straight from the POST response so
    // it appears immediately; the background invalidate then reconciles.
    onSuccess: (resp) => {
      qc.setQueryData<Category[]>(['categories', brandId], (old) => (old ? [...old, resp.data] : old))
      invalidateList()
      resetAdd()
    },
    onError: (e: unknown) => { invalidateList(); setFormError(apiErrorMessage(e, 'Failed to create category.')) },
  })

  const createGroup = useMutation({
    mutationFn: (name: string) => api.post('/reporting-groups', { name }, { params }),
    onSuccess: (resp) => {
      qc.setQueryData<ReportingGroup[]>(['reporting-groups', brandId], (old) => (old ? [...old, resp.data] : old))
      invalidateGroups()
      resetAdd()
    },
    onError: (e: unknown) => { invalidateGroups(); setFormError(apiErrorMessage(e, 'Failed to create reporting group.')) },
  })

  const resetAdd = () => { setAdding(null); setDraftName(''); setDraftGroupId(''); setFormError(null) }

  const toggleSelected = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const clearSelection = () => { setSelected(new Set()); setAssignMenuOpen(false) }

  const bulkAssign = async (reportingGroupId: string) => {
    await Promise.all([...selected].map((id) => patch.mutateAsync({ id, body: { reporting_group_id: reportingGroupId } })))
    clearSelection()
  }

  if (!brandId) {
    return <div className="flex items-center justify-center h-64 text-sm text-gray-400">No brand context available.</div>
  }

  const grouped = reportingGroups.map((g) => ({
    group: g,
    rows: categories.filter((c) => c.reporting_group_id === g.id),
  }))

  const allIds = categories.map((c) => c.id)
  const allSelected = allIds.length > 0 && allIds.every((id) => selected.has(id))

  return (
    <div className="p-4 sm:p-6 pb-24" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      <div className="max-w-3xl mx-auto">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Categories</h1>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Each category has a default button colour used across POS layouts. Grouped by reporting group.
            </p>
          </div>
          <div className="flex items-center gap-3 flex-none">
            <button
              onClick={() => { setAdding('group'); setDraftName(''); setFormError(null) }}
              className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-xs font-semibold text-gray-600 dark:text-gray-300 hover:border-brand-500 hover:text-brand-600 transition-colors"
            >
              + Reporting group
            </button>
            <button
              onClick={() => { setAdding('category'); setDraftName(''); setDraftGroupId(reportingGroups.find((g) => g.is_default)?.id ?? ''); setFormError(null) }}
              className="px-3 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
            >
              + Category
            </button>
          </div>
        </div>

        {isLoading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : (
          <>
            <div className="flex items-center gap-2 mb-4 text-xs font-medium text-gray-500 dark:text-gray-400">
              <button
                onClick={() => setSelected(allSelected ? new Set() : new Set(allIds))}
                className="flex items-center gap-1.5 hover:text-gray-700 dark:hover:text-gray-200"
              >
                <span className={`w-4 h-4 rounded border flex items-center justify-center ${allSelected ? 'bg-brand-600 border-brand-600 text-white' : 'border-gray-300 dark:border-gray-600'}`}>
                  {allSelected && '✓'}
                </span>
                Select all
              </button>
            </div>

            {adding && (
              <div className="flex flex-wrap items-center gap-3 bg-white dark:bg-gray-800 border border-brand-400 dark:border-brand-600 rounded-lg px-4 py-3 mb-4">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-brand-600 whitespace-nowrap">
                  {adding === 'category' ? 'New category' : 'New reporting group'}
                </span>
                <input
                  autoFocus
                  value={draftName}
                  onChange={(e) => setDraftName(e.target.value)}
                  placeholder={adding === 'category' ? 'Category name' : 'Reporting group name'}
                  className="flex-1 min-w-[140px] px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
                {adding === 'category' && (
                  <select
                    value={draftGroupId}
                    onChange={(e) => setDraftGroupId(e.target.value)}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  >
                    <option value="" disabled>Select a reporting group…</option>
                    {reportingGroups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                  </select>
                )}
                <div className="flex-1" />
                {formError && <p className="text-xs text-red-600">{formError}</p>}
                <button onClick={resetAdd} className="text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700">
                  Cancel
                </button>
                <button
                  onClick={() => {
                    setFormError(null)
                    if (adding === 'category') {
                      if (!draftName || !draftGroupId) return
                      createCategory.mutate({ name: draftName, brand_id: brandId, reporting_group_id: draftGroupId, display_order: 0 })
                    } else {
                      if (!draftName) return
                      createGroup.mutate(draftName)
                    }
                  }}
                  disabled={createCategory.isPending || createGroup.isPending}
                  className="px-3.5 py-2 bg-brand-600 text-white text-xs font-semibold rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors whitespace-nowrap"
                >
                  {createCategory.isPending || createGroup.isPending
                    ? 'Adding…'
                    : adding === 'category' ? 'Add category' : 'Add group'}
                </button>
              </div>
            )}

            <div className="space-y-4">
              {grouped.map(({ group, rows }) => (
                <div key={group.id} className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-visible">
                  <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100 dark:border-gray-700 bg-gray-50/60 dark:bg-gray-900/30 rounded-t-xl">
                    <button
                      onClick={() => setSelected((prev) => {
                        const next = new Set(prev)
                        const ids = rows.map((r) => r.id)
                        const allOn = ids.every((id) => next.has(id))
                        ids.forEach((id) => (allOn ? next.delete(id) : next.add(id)))
                        return next
                      })}
                      className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 ${rows.length > 0 && rows.every((r) => selected.has(r.id)) ? 'bg-brand-600 border-brand-600 text-white' : 'border-gray-300 dark:border-gray-600'}`}
                    >
                      {rows.length > 0 && rows.every((r) => selected.has(r.id)) && '✓'}
                    </button>
                    <div className="font-serif font-bold text-[15px] text-gray-900 dark:text-gray-100">
                      <EditableText
                        value={group.name}
                        disabled={group.is_system}
                        onSave={async (v) => { await patchGroup.mutateAsync({ id: group.id, body: { name: v } }) }}
                      />
                    </div>
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">reporting group</span>
                    <span className="ml-auto text-xs text-gray-400 dark:text-gray-500">{rows.length} {rows.length === 1 ? 'category' : 'categories'}</span>
                  </div>
                  {rows.length === 0 ? (
                    <div className="px-4 py-6 text-center text-xs text-gray-400 dark:text-gray-500">No categories yet.</div>
                  ) : (
                    rows.map((c) => (
                      <div
                        key={c.id}
                        onClick={() => toggleSelected(c.id)}
                        className={`flex items-center gap-3 px-4 py-3 border-b last:border-b-0 border-gray-100 dark:border-gray-700 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/40 ${selected.has(c.id) ? 'bg-brand-50 dark:bg-brand-950/40' : ''}`}
                      >
                        <span className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 ${selected.has(c.id) ? 'bg-brand-600 border-brand-600 text-white' : 'border-gray-300 dark:border-gray-600'}`}>
                          {selected.has(c.id) && '✓'}
                        </span>
                        <div onClick={(e) => e.stopPropagation()}>
                          <ColorSwatchPicker
                            value={c.default_color || DEFAULT_CATEGORY_COLOR}
                            onChange={(color) => patch.mutate({ id: c.id, body: { default_color: color } })}
                            title="Category colour"
                          />
                        </div>
                        <div className="text-sm font-medium text-gray-900 dark:text-gray-100" onClick={(e) => e.stopPropagation()}>
                          <EditableText
                            value={c.name}
                            disabled={c.is_system}
                            onSave={async (v) => { await patch.mutateAsync({ id: c.id, body: { name: v } }) }}
                          />
                        </div>
                        {!c.is_active && <StatusBadge status="disabled" />}
                        <div className="flex-1" />
                        <span className="text-[11px] font-medium text-gray-400 dark:text-gray-500 border border-gray-200 dark:border-gray-600 rounded-md px-2 py-1 whitespace-nowrap">
                          {group.name}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              ))}
              {reportingGroups.length === 0 && (
                <p className="text-sm text-gray-400 text-center py-8">No reporting groups yet — add one to start creating categories.</p>
              )}
            </div>
          </>
        )}
      </div>

      {selected.size > 0 && (
        <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-30 flex items-center gap-4 bg-gray-900 dark:bg-gray-950 text-white rounded-xl px-4 py-3 shadow-2xl">
          <span className="text-sm font-semibold whitespace-nowrap">{selected.size} selected</span>
          <div className="relative">
            <button
              onClick={() => setAssignMenuOpen((o) => !o)}
              className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold px-3.5 py-2 rounded-lg whitespace-nowrap"
            >
              Assign to reporting group <span>⌄</span>
            </button>
            {assignMenuOpen && (
              <div className="absolute bottom-full left-0 mb-2 w-56 max-h-64 overflow-auto bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-xl p-1">
                <div className="px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
                  Reporting groups
                </div>
                {reportingGroups.map((g) => (
                  <button
                    key={g.id}
                    onClick={() => bulkAssign(g.id)}
                    className="w-full flex items-center justify-between px-2.5 py-2 rounded-md text-xs font-medium text-gray-900 dark:text-gray-100 hover:bg-brand-50 dark:hover:bg-brand-950/40 hover:text-brand-600"
                  >
                    <span>{g.name}</span>
                    <span className="text-gray-400 dark:text-gray-500">{categories.filter((c) => c.reporting_group_id === g.id).length}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <button onClick={clearSelection} className="text-xs font-medium text-white/70 hover:text-white whitespace-nowrap">
            Clear
          </button>
        </div>
      )}
    </div>
  )
}
