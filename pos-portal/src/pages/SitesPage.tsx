/** CRUD page for Sites (third tier of the hierarchy). */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/axios'
import type { Brand, Site } from '../types'
import { EntityIdChip } from '../components/EntityIdChip'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'

async function fetchSites(): Promise<Site[]> {
  const { data } = await api.get('/sites/', { params: { limit: 200 } })
  return data
}

async function fetchBrands(): Promise<Brand[]> {
  const { data } = await api.get('/brands/', { params: { limit: 200 } })
  return data
}

export function SitesPage() {
  const qc = useQueryClient()
  const { data: sites = [], isLoading } = useQuery({ queryKey: ['sites'], queryFn: fetchSites })
  const { data: brands = [] } = useQuery({ queryKey: ['brands'], queryFn: fetchBrands })

  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<Site | null>(null)
  const [name, setName] = useState('')
  const [brandId, setBrandId] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['sites'] })

  const createMutation = useMutation({
    mutationFn: ({ name, brand_id }: { name: string; brand_id: string }) =>
      api.post('/sites/', { name, brand_id }),
    onSuccess: () => { invalidate(); setShowCreate(false); setName(''); setBrandId('') },
    onError: () => setFormError('Failed to create site.'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      api.patch(`/sites/${id}`, { name }),
    onSuccess: () => { invalidate(); setEditing(null); setName('') },
    onError: () => setFormError('Failed to update site.'),
  })

  const suspendMutation = useMutation({
    mutationFn: (id: string) => api.post(`/sites/${id}/suspend`),
    onSuccess: invalidate,
  })

  const activateMutation = useMutation({
    mutationFn: (id: string) => api.post(`/sites/${id}/activate`),
    onSuccess: invalidate,
  })

  const brandName = (id: string) => brands.find((b) => b.id === id)?.name ?? id.slice(0, 8)

  const openCreate = () => {
    setName('')
    setBrandId(brands[0]?.id ?? '')
    setFormError(null)
    setShowCreate(true)
  }
  const openEdit = (s: Site) => { setName(s.name); setFormError(null); setEditing(s) }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    if (editing) updateMutation.mutate({ id: editing.id, name })
    else createMutation.mutate({ name, brand_id: brandId })
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Sites</h1>
        <button
          onClick={openCreate}
          className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New Site
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
                <th className="px-4 py-3">Brand ID</th>
                <th className="px-4 py-3">Brand</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {sites.map((s) => (
                <tr key={s.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3"><EntityIdChip id={s.id} /></td>
                  <td className="px-4 py-3 font-medium text-gray-900">{s.name}</td>
                  <td className="px-4 py-3"><EntityIdChip id={s.brand_id} /></td>
                  <td className="px-4 py-3 text-gray-500">{brandName(s.brand_id)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={s.is_active ? 'active' : 'suspended'} />
                  </td>
                  <td className="px-4 py-3 flex gap-2">
                    <button onClick={() => openEdit(s)} className="text-indigo-600 hover:underline text-xs">Edit</button>
                    {s.is_active ? (
                      <button onClick={() => suspendMutation.mutate(s.id)} className="text-amber-600 hover:underline text-xs">Suspend</button>
                    ) : (
                      <button onClick={() => activateMutation.mutate(s.id)} className="text-green-600 hover:underline text-xs">Activate</button>
                    )}
                  </td>
                </tr>
              ))}
              {sites.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-400">No sites yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {(showCreate || editing) && (
        <Modal
          title={editing ? 'Edit Site' : 'New Site'}
          onClose={() => { setShowCreate(false); setEditing(null) }}
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            {!editing && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Brand</label>
                <select
                  value={brandId}
                  onChange={(e) => setBrandId(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {brands.map((b) => (
                    <option key={b.id} value={b.id}>{b.name}</option>
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
                placeholder="Sydney CBD"
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
