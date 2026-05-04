/** CRUD page for Groups (top of the multi-tenant hierarchy). */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/axios'
import type { Group } from '../types'
import { EntityIdChip } from '../components/EntityIdChip'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'

async function fetchGroups(): Promise<Group[]> {
  const { data } = await api.get('/groups/', { params: { limit: 200 } })
  return data
}

export function GroupsPage() {
  const qc = useQueryClient()
  const { data: groups = [], isLoading } = useQuery({ queryKey: ['groups'], queryFn: fetchGroups })

  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<Group | null>(null)
  const [name, setName] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['groups'] })

  const createMutation = useMutation({
    mutationFn: (name: string) => api.post('/groups/', { name }),
    onSuccess: () => { invalidate(); setShowCreate(false); setName('') },
    onError: () => setFormError('Failed to create group.'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      api.patch(`/groups/${id}`, { name }),
    onSuccess: () => { invalidate(); setEditing(null); setName('') },
    onError: () => setFormError('Failed to update group.'),
  })

  const suspendMutation = useMutation({
    mutationFn: (id: string) => api.post(`/groups/${id}/suspend`),
    onSuccess: invalidate,
  })

  const activateMutation = useMutation({
    mutationFn: (id: string) => api.post(`/groups/${id}/activate`),
    onSuccess: invalidate,
  })

  const openCreate = () => { setName(''); setFormError(null); setShowCreate(true) }
  const openEdit = (g: Group) => { setName(g.name); setFormError(null); setEditing(g) }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    if (editing) updateMutation.mutate({ id: editing.id, name })
    else createMutation.mutate(name)
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Groups</h1>
        <button
          onClick={openCreate}
          className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New Group
        </button>
      </div>

      {isLoading ? (
        <div className="text-gray-400 text-sm">Loading…</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {groups.map((g) => (
                <tr key={g.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3"><EntityIdChip id={g.id} /></td>
                  <td className="px-4 py-3 font-medium text-gray-900">{g.name}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={g.is_active ? 'active' : 'suspended'} />
                  </td>
                  <td className="px-4 py-3 text-gray-400">{new Date(g.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3 flex gap-2">
                    <button onClick={() => openEdit(g)} className="text-indigo-600 hover:underline text-xs">Edit</button>
                    {g.is_active ? (
                      <button onClick={() => suspendMutation.mutate(g.id)} className="text-amber-600 hover:underline text-xs">Suspend</button>
                    ) : (
                      <button onClick={() => activateMutation.mutate(g.id)} className="text-green-600 hover:underline text-xs">Activate</button>
                    )}
                  </td>
                </tr>
              ))}
              {groups.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-400">No groups yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {(showCreate || editing) && (
        <Modal
          title={editing ? 'Edit Group' : 'New Group'}
          onClose={() => { setShowCreate(false); setEditing(null) }}
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                minLength={1}
                autoFocus
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Acme Corp"
              />
            </div>
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => { setShowCreate(false); setEditing(null) }} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">Cancel</button>
              <button type="submit" className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg">
                {editing ? 'Save' : 'Create'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
