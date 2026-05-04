/** CRUD page for Brands (second tier of the hierarchy). */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/axios'
import type { Brand, Group } from '../types'
import { EntityIdChip } from '../components/EntityIdChip'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'

async function fetchBrands(): Promise<Brand[]> {
  const { data } = await api.get('/brands/', { params: { limit: 200 } })
  return data
}

async function fetchGroups(): Promise<Group[]> {
  const { data } = await api.get('/groups/', { params: { limit: 200 } })
  return data
}

export function BrandsPage() {
  const qc = useQueryClient()
  const { data: brands = [], isLoading } = useQuery({ queryKey: ['brands'], queryFn: fetchBrands })
  const { data: groups = [] } = useQuery({ queryKey: ['groups'], queryFn: fetchGroups })

  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<Brand | null>(null)
  const [name, setName] = useState('')
  const [groupId, setGroupId] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['brands'] })

  const createMutation = useMutation({
    mutationFn: ({ name, group_id }: { name: string; group_id: string }) =>
      api.post('/brands/', { name, group_id }),
    onSuccess: () => { invalidate(); setShowCreate(false); setName(''); setGroupId('') },
    onError: () => setFormError('Failed to create brand.'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      api.patch(`/brands/${id}`, { name }),
    onSuccess: () => { invalidate(); setEditing(null); setName('') },
    onError: () => setFormError('Failed to update brand.'),
  })

  const suspendMutation = useMutation({
    mutationFn: (id: string) => api.post(`/brands/${id}/suspend`),
    onSuccess: invalidate,
  })

  const activateMutation = useMutation({
    mutationFn: (id: string) => api.post(`/brands/${id}/activate`),
    onSuccess: invalidate,
  })

  const groupName = (id: string) => groups.find((g) => g.id === id)?.name ?? id.slice(0, 8)

  const openCreate = () => {
    setName('')
    setGroupId(groups[0]?.id ?? '')
    setFormError(null)
    setShowCreate(true)
  }
  const openEdit = (b: Brand) => { setName(b.name); setFormError(null); setEditing(b) }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    if (editing) updateMutation.mutate({ id: editing.id, name })
    else createMutation.mutate({ name, group_id: groupId })
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Brands</h1>
        <button
          onClick={openCreate}
          className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New Brand
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
                <th className="px-4 py-3">Group</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {brands.map((b) => (
                <tr key={b.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3"><EntityIdChip id={b.id} /></td>
                  <td className="px-4 py-3 font-medium text-gray-900">{b.name}</td>
                  <td className="px-4 py-3 text-gray-500">
                    <div className="flex flex-col gap-0.5">
                      <span>{groupName(b.group_id)}</span>
                      <EntityIdChip id={b.group_id} />
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={b.is_active ? 'active' : 'suspended'} />
                  </td>
                  <td className="px-4 py-3 flex gap-2">
                    <button onClick={() => openEdit(b)} className="text-indigo-600 hover:underline text-xs">Edit</button>
                    {b.is_active ? (
                      <button onClick={() => suspendMutation.mutate(b.id)} className="text-amber-600 hover:underline text-xs">Suspend</button>
                    ) : (
                      <button onClick={() => activateMutation.mutate(b.id)} className="text-green-600 hover:underline text-xs">Activate</button>
                    )}
                  </td>
                </tr>
              ))}
              {brands.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-400">No brands yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {(showCreate || editing) && (
        <Modal
          title={editing ? 'Edit Brand' : 'New Brand'}
          onClose={() => { setShowCreate(false); setEditing(null) }}
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            {!editing && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Group</label>
                <select
                  value={groupId}
                  onChange={(e) => setGroupId(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {groups.map((g) => (
                    <option key={g.id} value={g.id}>{g.name}</option>
                  ))}
                </select>
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                autoFocus
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Burger Chain"
              />
            </div>
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => { setShowCreate(false); setEditing(null) }} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">Cancel</button>
              <button type="submit" disabled={createMutation.isPending || updateMutation.isPending} className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg">
                {editing ? 'Save' : 'Create'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
