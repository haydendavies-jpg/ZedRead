/** Product categories management page — list, create, rename categories. */

import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { Modal } from '../../components/Modal'
import { StatusBadge } from '../../components/StatusBadge'
import type { Category, ReportingGroup } from '../../types'

export function CategoriesPage() {
  const qc = useQueryClient()
  const brandId = useMgmtBrandId()
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<Category | null>(null)

  const params = brandId ? { brand_id: brandId } : {}

  const { data: categories = [], isLoading } = useQuery<Category[]>({
    queryKey: ['categories', brandId],
    queryFn: () => api.get('/categories', { params }).then((r) => r.data),
    enabled: brandId !== undefined,
  })

  const deactivate = useMutation({
    mutationFn: (id: string) => api.patch(`/categories/${id}`, { is_active: false }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['categories', brandId] }),
  })

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
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm min-w-[400px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Type</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {categories.map((c) => (
                <tr key={c.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{c.name}</td>
                  <td className="px-4 py-3 text-gray-500">{c.is_system ? 'System' : 'Custom'}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={c.is_active ? "active" : "disabled"} />
                  </td>
                  <td className="px-4 py-3 text-right space-x-2">
                    {!c.is_system && (
                      <>
                        <button
                          onClick={() => setEditing(c)}
                          className="text-brand-600 hover:text-brand-800 text-xs font-medium"
                        >
                          Rename
                        </button>
                        {c.is_active && (
                          <button
                            onClick={() => deactivate.mutate(c.id)}
                            className="text-red-500 hover:text-red-700 text-xs font-medium"
                          >
                            Deactivate
                          </button>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {categories.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-gray-400">
                    No categories yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {(showCreate || editing) && (
        <CategoryFormModal
          category={editing}
          brandId={brandId}
          onClose={() => { setShowCreate(false); setEditing(null) }}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ['categories', brandId] })
            setShowCreate(false)
            setEditing(null)
          }}
        />
      )}
    </div>
  )
}

interface CategoryFormProps {
  category: Category | null
  brandId: string
  onClose: () => void
  onSaved: () => void
}

function CategoryFormModal({ category, brandId, onClose, onSaved }: CategoryFormProps) {
  const [name, setName] = useState(category?.name ?? '')
  const [reportingGroupId, setReportingGroupId] = useState(category?.reporting_group_id ?? '')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const params = brandId ? { brand_id: brandId } : {}

  const { data: reportingGroups = [] } = useQuery<ReportingGroup[]>({
    queryKey: ['reporting-groups', brandId],
    queryFn: () => api.get('/reporting-groups', { params }).then((r) => r.data),
  })

  // Every category requires a reporting group — default new categories to the brand's default group
  useEffect(() => {
    if (!category && !reportingGroupId && reportingGroups.length > 0) {
      const defaultGroup = reportingGroups.find((g) => g.is_default) ?? reportingGroups[0]
      setReportingGroupId(defaultGroup.id)
    }
  }, [category, reportingGroupId, reportingGroups])

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      if (category) {
        await api.patch(
          `/categories/${category.id}`,
          { name, reporting_group_id: reportingGroupId },
          { params }
        )
      } else {
        await api.post(
          '/categories',
          { name, brand_id: brandId, reporting_group_id: reportingGroupId, display_order: 0 },
          { params }
        )
      }
      onSaved()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Failed to save category.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title={category ? 'Edit category' : 'Add category'} onClose={onClose}>
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
            value={reportingGroupId}
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
            disabled={saving || !name || !reportingGroupId}
            className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
