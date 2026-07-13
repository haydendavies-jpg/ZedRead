/** Reporting groups management page — list, create, rename reporting groups (Stage 16).
 *
 * Stage 20: inline cell edit for the name (renaming happens directly in the table now,
 * so the old separate rename modal is gone), plus a shared filter bar.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { Modal } from '../../components/Modal'
import { EntityIdChip } from '../../components/EntityIdChip'
import { EditableText } from '../../components/EditableCell'
import { FilterBar, type FilterConfig } from '../../components/FilterBar'
import { apiErrorMessage } from '../../utils/apiError'
import type { ReportingGroup } from '../../types'

export function ReportingGroupsPage() {
  const qc = useQueryClient()
  const brandId = useMgmtBrandId()
  const [showCreate, setShowCreate] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')

  const params = brandId ? { brand_id: brandId } : {}

  const { data: reportingGroups = [], isLoading } = useQuery<ReportingGroup[]>({
    queryKey: ['reporting-groups', brandId],
    queryFn: () => api.get('/reporting-groups', { params }).then((r) => r.data),
    enabled: brandId !== undefined,
  })

  const invalidateList = () => qc.invalidateQueries({ queryKey: ['reporting-groups', brandId] })

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.patch(`/reporting-groups/${id}`, body, { params }),
    onSuccess: invalidateList,
    onError: invalidateList,
  })

  const deleteGroup = useMutation({
    mutationFn: (id: string) => api.delete(`/reporting-groups/${id}`, { params }),
    onSuccess: () => { invalidateList(); setDeleteError(null) },
    onError: (e: unknown) => {
      invalidateList()
      setDeleteError(apiErrorMessage(e, 'Failed to delete reporting group.'))
    },
  })

  const filtered = reportingGroups.filter((g) => {
    if (search && !g.name.toLowerCase().includes(search.toLowerCase()) && !g.ref.toLowerCase().includes(search.toLowerCase())) return false
    if (typeFilter === 'default' && !g.is_default) return false
    if (typeFilter === 'custom' && g.is_default) return false
    return true
  })

  const hasFilters = !!(search || typeFilter)
  const clearFilters = () => { setSearch(''); setTypeFilter('') }

  const filters: FilterConfig[] = [
    {
      label: 'Type',
      value: typeFilter,
      onChange: setTypeFilter,
      options: [
        { value: '', label: 'All types' },
        { value: 'default', label: 'Default' },
        { value: 'custom', label: 'Custom' },
      ],
    },
  ]

  if (!brandId) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-gray-400 dark:text-gray-500">
        No brand context available.
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Reporting Groups</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="px-3 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
        >
          Add reporting group
        </button>
      </div>

      {deleteError && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-4">
          {deleteError}
        </p>
      )}

      {isLoading ? (
        <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
      ) : (
        <>
          <FilterBar
            search={search}
            onSearchChange={setSearch}
            searchPlaceholder="Search by name or code…"
            filters={filters}
            hasFilters={hasFilters}
            onClear={clearFilters}
            resultCount={filtered.length}
            totalCount={reportingGroups.length}
          />

          <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700">
            <table className="w-full text-sm min-w-[500px]">
              <thead className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-400">ID</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-400">Name</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-400">Type</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {filtered.map((g) => (
                  <tr key={g.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/60">
                    <td className="px-4 py-3">
                      <EntityIdChip id={g.id} ref={g.ref} />
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">
                      <EditableText
                        value={g.name}
                        disabled={g.is_system}
                        onSave={async (v) => { await patch.mutateAsync({ id: g.id, body: { name: v } }) }}
                      />
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{g.is_default ? 'Default' : 'Custom'}</td>
                    <td className="px-4 py-3 text-right">
                      {!g.is_system && (
                        <button
                          onClick={() => { setDeleteError(null); deleteGroup.mutate(g.id) }}
                          className="text-red-500 hover:text-red-700 text-xs font-medium"
                        >
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-gray-400 dark:text-gray-500">
                      {reportingGroups.length === 0 ? 'No reporting groups yet.' : 'No reporting groups match the current filters.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {showCreate && (
        <ReportingGroupCreateModal
          brandId={brandId}
          onClose={() => setShowCreate(false)}
          onSaved={() => {
            invalidateList()
            setShowCreate(false)
          }}
        />
      )}
    </div>
  )
}

interface ReportingGroupCreateFormProps {
  brandId: string
  onClose: () => void
  onSaved: () => void
}

/** Name is the only mutable field, and it's inline-editable in the table once a group
 * exists — this modal only handles the create flow. */
function ReportingGroupCreateModal({ brandId, onClose, onSaved }: ReportingGroupCreateFormProps) {
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const params = brandId ? { brand_id: brandId } : {}
      await api.post('/reporting-groups', { name }, { params })
      onSaved()
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'Failed to save reporting group.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="Add reporting group" onClose={onClose}>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        {error && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900">
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !name}
            className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
