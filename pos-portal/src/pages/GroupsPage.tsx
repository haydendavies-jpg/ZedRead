/** CRUD page for Groups (top of the multi-tenant hierarchy). */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/axios'
import type { Group } from '../types'
import { Link } from 'react-router-dom'
import { EntityIdChip } from '../components/EntityIdChip'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'
import { CompanyProfileFields, type CompanyProfileValues } from '../components/CompanyProfileFields'
import { DEFAULT_COMPANY_PROFILE_VALUES, confirmCurrencyChange } from '../utils/companyProfile'

async function fetchGroups(): Promise<Group[]> {
  const { data } = await api.get('/groups/', { params: { limit: 200 } })
  return data
}

export function GroupsPage() {
  const qc = useQueryClient()
  const { data: groups = [], isLoading } = useQuery({ queryKey: ['groups'], queryFn: fetchGroups })

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<Group | null>(null)
  const [name, setName] = useState('')
  const [profile, setProfile] = useState<CompanyProfileValues>(DEFAULT_COMPANY_PROFILE_VALUES)
  const [formError, setFormError] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['groups'] })

  const createMutation = useMutation({
    mutationFn: (body: { name: string } & CompanyProfileValues) => api.post('/groups/', body),
    onSuccess: () => { invalidate(); setShowCreate(false); setName(''); setProfile(DEFAULT_COMPANY_PROFILE_VALUES) },
    onError: () => { invalidate(); setFormError('Failed to create group.') },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { name: string } & CompanyProfileValues }) =>
      api.patch(`/groups/${id}`, body),
    onSuccess: () => { invalidate(); setEditing(null); setName('') },
    onError: () => { invalidate(); setFormError('Failed to update group.') },
  })

  const suspendMutation = useMutation({
    mutationFn: (id: string) => api.post(`/groups/${id}/suspend`),
    onSuccess: invalidate,
  })

  const activateMutation = useMutation({
    mutationFn: (id: string) => api.post(`/groups/${id}/activate`),
    onSuccess: invalidate,
  })

  const openCreate = () => {
    setName('')
    setProfile(DEFAULT_COMPANY_PROFILE_VALUES)
    setFormError(null)
    setShowCreate(true)
  }
  const openEdit = (g: Group) => {
    setName(g.name)
    setProfile({
      timezone: g.timezone,
      currency: g.currency,
      country: g.country,
      tax_id_value: g.tax_id_value ?? '',
      billing_email: g.billing_email ?? '',
    })
    setFormError(null)
    setEditing(g)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    if (editing) {
      if (!confirmCurrencyChange(editing.currency, profile.currency, 'group')) return
      updateMutation.mutate({ id: editing.id, body: { name, ...profile } })
    } else {
      createMutation.mutate({ name, ...profile })
    }
  }

  const filtered = groups.filter((g) => {
    if (search && !g.name.toLowerCase().includes(search.toLowerCase())) return false
    if (statusFilter === 'active' && !g.is_active) return false
    if (statusFilter === 'suspended' && g.is_active) return false
    return true
  })

  return (
    <div className="p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Groups</h1>
        <button
          onClick={openCreate}
          className="bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New Group
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <input
          type="text"
          placeholder="Search by name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 w-56"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
        </select>
        {(search || statusFilter) && (
          <button
            onClick={() => { setSearch(''); setStatusFilter('') }}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            Clear filters
          </button>
        )}
        <span className="text-xs text-gray-400 ml-auto">
          {filtered.length} of {groups.length}
        </span>
      </div>

      {isLoading ? (
        <div className="text-gray-400 text-sm">Loading…</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm min-w-[600px]">
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
              {filtered.map((g) => (
                <tr key={g.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3"><EntityIdChip id={g.id} ref={g.ref} /></td>
                  <td className="px-4 py-3 font-medium text-gray-900">
                    <Link to={`/groups/${g.id}`} className="hover:text-brand-600 transition-colors">
                      {g.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={g.is_active ? 'active' : 'suspended'} />
                  </td>
                  <td className="px-4 py-3 text-gray-400">{new Date(g.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3 flex gap-2">
                    <button onClick={() => openEdit(g)} className="text-brand-600 hover:underline text-xs">Edit</button>
                    {g.is_active ? (
                      <button onClick={() => suspendMutation.mutate(g.id)} className="text-amber-600 hover:underline text-xs">Suspend</button>
                    ) : (
                      <button onClick={() => activateMutation.mutate(g.id)} className="text-green-600 hover:underline text-xs">Activate</button>
                    )}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  {groups.length === 0 ? 'No groups yet.' : 'No groups match the current filters.'}
                </td></tr>
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
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="Acme Corp"
              />
            </div>
            <CompanyProfileFields values={profile} onChange={setProfile} />
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => { setShowCreate(false); setEditing(null) }} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">Cancel</button>
              <button type="submit" disabled={createMutation.isPending || updateMutation.isPending} className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg">
                {editing ? 'Save' : 'Create'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
