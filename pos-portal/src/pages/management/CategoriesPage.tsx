/** Product categories management page — list, create, rename categories.
 *
 * Stage 20: table shows the Reporting Group column, supports inline cell edit
 * (name, reporting group, status) and a shared filter bar.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { Modal } from '../../components/Modal'
import { StatusBadge } from '../../components/StatusBadge'
import { EntityIdChip } from '../../components/EntityIdChip'
import { EditableText, EditableSelect } from '../../components/EditableCell'
import { FilterBar, type FilterConfig } from '../../components/FilterBar'
import { apiErrorMessage } from '../../utils/apiError'
import type { Category, ReportingGroup } from '../../types'

export function CategoriesPage() {
  const qc = useQueryClient()
  const brandId = useMgmtBrandId()
  const [showCreate, setShowCreate] = useState(false)

  const [search, setSearch] = useState('')
  const [reportingGroupFilter, setReportingGroupFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const params = brandId ? { brand_id: brandId } : {}

  const { data: categories = [], isLoading } = useQuery<Category[]>({
    queryKey: ['categories', brandId],
    queryFn: () => api.get('/categories', { params: { ...params, include_inactive: true, limit: 500 } }).then((r) => r.data),
    enabled: brandId !== undefined,
  })

  const { data: reportingGroups = [] } = useQuery<ReportingGroup[]>({
    queryKey: ['reporting-groups', brandId],
    queryFn: () => api.get('/reporting-groups', { params: { ...params, limit: 200 } }).then((r) => r.data),
    enabled: !!brandId,
  })

  const invalidateList = () => qc.invalidateQueries({ queryKey: ['categories', brandId] })

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.patch(`/categories/${id}`, body, { params }),
    onSuccess: invalidateList,
    onError: invalidateList,
  })

  const reportingGroupName = (id: string) => reportingGroups.find((g) => g.id === id)?.name ?? id.slice(0, 8)
  const reportingGroupOptions = reportingGroups.map((g) => ({ value: g.id, label: g.name }))

  const filtered = categories.filter((c) => {
    if (search && !c.name.toLowerCase().includes(search.toLowerCase()) && !c.ref.toLowerCase().includes(search.toLowerCase())) return false
    if (reportingGroupFilter && c.reporting_group_id !== reportingGroupFilter) return false
    if (statusFilter === 'active' && !c.is_active) return false
    if (statusFilter === 'inactive' && c.is_active) return false
    return true
  })

  const hasFilters = !!(search || reportingGroupFilter || statusFilter)
  const clearFilters = () => { setSearch(''); setReportingGroupFilter(''); setStatusFilter('') }

  const filters: FilterConfig[] = [
    {
      label: 'Reporting Group',
      value: reportingGroupFilter,
      onChange: setReportingGroupFilter,
      options: [{ value: '', label: 'All reporting groups' }, ...reportingGroupOptions],
    },
    {
      label: 'Status',
      value: statusFilter,
      onChange: setStatusFilter,
      options: [
        { value: '', label: 'All statuses' },
        { value: 'active', label: 'Active' },
        { value: 'inactive', label: 'Inactive' },
      ],
    },
  ]

  if (!brandId) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-gray-400">
        No brand context available.
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Categories</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="px-3 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
        >
          Add category
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400">Loading…</p>
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
            totalCount={categories.length}
          />

          <div className="overflow-x-auto rounded-xl border border-gray-200">
            <table className="w-full text-sm min-w-[600px]">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">ID</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Reporting Group</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Type</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map((c) => (
                  <tr key={c.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3"><EntityIdChip id={c.id} ref={c.ref} /></td>
                    <td className="px-4 py-3 font-medium text-gray-900">
                      <EditableText
                        value={c.name}
                        disabled={c.is_system}
                        onSave={async (v) => { await patch.mutateAsync({ id: c.id, body: { name: v } }) }}
                      />
                    </td>
                    <td className="px-4 py-3 text-gray-700">
                      <EditableSelect
                        value={c.reporting_group_id}
                        options={reportingGroupOptions.length > 0 ? reportingGroupOptions : [{ value: c.reporting_group_id, label: reportingGroupName(c.reporting_group_id) }]}
                        onSave={async (v) => { await patch.mutateAsync({ id: c.id, body: { reporting_group_id: v } }) }}
                      />
                    </td>
                    <td className="px-4 py-3 text-gray-500">{c.is_system ? 'System' : 'Custom'}</td>
                    <td className="px-4 py-3">
                      <StatusBadge
                        status={c.is_active ? 'active' : 'disabled'}
                        disabled={c.is_system}
                        title={c.is_system ? undefined : (c.is_active ? 'Click to deactivate' : 'Click to activate')}
                        onClick={() => patch.mutate({ id: c.id, body: { is_active: !c.is_active } })}
                      />
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                      {categories.length === 0 ? 'No categories yet.' : 'No categories match the current filters.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {showCreate && (
        <CategoryCreateModal
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

interface CategoryCreateFormProps {
  brandId: string
  onClose: () => void
  onSaved: () => void
}

/** Name + Reporting Group are the only mutable fields, and both are inline-editable
 * in the table once a category exists — this modal only handles the create flow. */
function CategoryCreateModal({ brandId, onClose, onSaved }: CategoryCreateFormProps) {
  const [name, setName] = useState('')
  const [reportingGroupId, setReportingGroupId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const params = brandId ? { brand_id: brandId } : {}

  const { data: reportingGroups = [] } = useQuery<ReportingGroup[]>({
    queryKey: ['reporting-groups', brandId],
    queryFn: () => api.get('/reporting-groups', { params }).then((r) => r.data),
  })

  // Every category requires a reporting group — default new categories to the brand's default
  // group, computed directly at render time rather than synced via an effect (setState-in-effect
  // is a lint smell — there's no external system here to synchronize with).
  const defaultGroupId = reportingGroups.find((g) => g.is_default)?.id ?? reportingGroups[0]?.id ?? ''
  const effectiveReportingGroupId = reportingGroupId || defaultGroupId

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await api.post(
        '/categories',
        { name, brand_id: brandId, reporting_group_id: effectiveReportingGroupId, display_order: 0 },
        { params }
      )
      onSaved()
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'Failed to save category.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="Add category" onClose={onClose}>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Reporting Group</label>
          <select
            value={effectiveReportingGroupId}
            onChange={(e) => setReportingGroupId(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="" disabled>Select a reporting group…</option>
            {reportingGroups.map((g) => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>
        </div>
        {error && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900">
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !name || !effectiveReportingGroupId}
            className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
