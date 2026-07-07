/** Reporting groups management page — list, create, rename reporting groups (Stage 16). */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { Modal } from '../../components/Modal'
import { EntityIdChip } from '../../components/EntityIdChip'
import type { ReportingGroup } from '../../types'

export function ReportingGroupsPage() {
  const qc = useQueryClient()
  const brandId = useMgmtBrandId()
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<ReportingGroup | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const params = brandId ? { brand_id: brandId } : {}

  const { data: reportingGroups = [], isLoading } = useQuery<ReportingGroup[]>({
    queryKey: ['reporting-groups', brandId],
    queryFn: () => api.get('/reporting-groups', { params }).then((r) => r.data),
    enabled: brandId !== undefined,
  })

  const invalidateList = () => qc.invalidateQueries({ queryKey: ['reporting-groups', brandId] })

  const deleteGroup = useMutation({
    mutationFn: (id: string) => api.delete(`/reporting-groups/${id}`, { params }),
    onSuccess: () => { invalidateList(); setDeleteError(null) },
    onError: (e: any) => {
      invalidateList()
      setDeleteError(e?.response?.data?.detail ?? 'Failed to delete reporting group.')
    },
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
        <h1 className="text-xl font-semibold text-gray-900">Reporting Groups</h1>
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
        <p className="text-sm text-gray-400">Loading…</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm min-w-[500px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">ID</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Type</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {reportingGroups.map((g) => (
                <tr key={g.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <EntityIdChip id={g.id} ref={g.ref} />
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-900">{g.name}</td>
                  <td className="px-4 py-3 text-gray-500">{g.is_default ? 'Default' : 'Custom'}</td>
                  <td className="px-4 py-3 text-right space-x-2">
                    {!g.is_system && (
                      <>
                        <button
                          onClick={() => setEditing(g)}
                          className="text-brand-600 hover:text-brand-800 text-xs font-medium"
                        >
                          Rename
                        </button>
                        <button
                          onClick={() => { setDeleteError(null); deleteGroup.mutate(g.id) }}
                          className="text-red-500 hover:text-red-700 text-xs font-medium"
                        >
                          Delete
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {reportingGroups.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-gray-400">
                    No reporting groups yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {(showCreate || editing) && (
        <ReportingGroupFormModal
          reportingGroup={editing}
          brandId={brandId}
          onClose={() => { setShowCreate(false); setEditing(null) }}
          onSaved={() => {
            invalidateList()
            setShowCreate(false)
            setEditing(null)
          }}
        />
      )}
    </div>
  )
}

interface ReportingGroupFormProps {
  reportingGroup: ReportingGroup | null
  brandId: string
  onClose: () => void
  onSaved: () => void
}

function ReportingGroupFormModal({ reportingGroup, brandId, onClose, onSaved }: ReportingGroupFormProps) {
  const [name, setName] = useState(reportingGroup?.name ?? '')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const params = brandId ? { brand_id: brandId } : {}
      if (reportingGroup) {
        await api.patch(`/reporting-groups/${reportingGroup.id}`, { name }, { params })
      } else {
        await api.post('/reporting-groups', { name }, { params })
      }
      onSaved()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Failed to save reporting group.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title={reportingGroup ? 'Rename reporting group' : 'Add reporting group'} onClose={onClose}>
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
