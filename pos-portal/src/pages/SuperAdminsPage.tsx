/** SuperAdmins management page — Admin-role SuperAdmin only. */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, fetchAll } from '../api/axios'
import { useAuth } from '../context/AuthContext'
import type { SuperAdmin } from '../types'
import { EntityIdChip } from '../components/EntityIdChip'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'

async function fetchSuperAdmins(): Promise<SuperAdmin[]> {
  return fetchAll<SuperAdmin>('/portal-users/')
}

const ROLES = [
  { value: 'admin', label: 'Admin' },
  { value: 'reseller_staff', label: 'Reseller' },
] as const

export function SuperAdminsPage() {
  const { user: me } = useAuth()
  const qc = useQueryClient()
  const { data: users = [], isLoading } = useQuery({ queryKey: ['superadmins'], queryFn: fetchSuperAdmins })

  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ email: '', name: '', password: '', role: 'admin' })
  const [formError, setFormError] = useState<string | null>(null)

  const [editUser, setEditUser] = useState<SuperAdmin | null>(null)
  const [editForm, setEditForm] = useState({ name: '', role: '' })
  const [editError, setEditError] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['superadmins'] })

  const createMutation = useMutation({
    mutationFn: (payload: typeof form) => api.post('/portal-users/', payload),
    onSuccess: () => {
      invalidate()
      setShowCreate(false)
      setForm({ email: '', name: '', password: '', role: 'admin' })
    },

    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setFormError(msg ?? 'Failed to create user.')
    },
  })

  const suspendMutation = useMutation({
    mutationFn: (id: string) => api.post(`/portal-users/${id}/suspend`),
    onSuccess: invalidate,
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      alert(msg ?? 'Failed to suspend user.')
    },
  })

  const activateMutation = useMutation({
    mutationFn: (id: string) => api.post(`/portal-users/${id}/activate`),
    onSuccess: invalidate,
  })

  const editMutation = useMutation({
    mutationFn: ({ id, name, role }: { id: string; name: string; role: string }) =>
      api.patch(`/portal-users/${id}`, { name, role }),
    onSuccess: () => {
      invalidate()
      setEditUser(null)
    },
    onError: (e: unknown) => {
      invalidate()
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setEditError(msg ?? 'Failed to update user.')
    },
  })

  const openEdit = (u: SuperAdmin) => {
    setEditForm({ name: u.name, role: u.role })
    setEditError(null)
    setEditUser(u)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    createMutation.mutate(form)
  }

  const filtered = users.filter((u) => {
    if (search) {
      const q = search.toLowerCase()
      if (!u.name.toLowerCase().includes(q) && !u.email.toLowerCase().includes(q)) return false
    }
    if (roleFilter && u.role !== roleFilter) return false
    if (statusFilter === 'active' && !u.is_active) return false
    if (statusFilter === 'suspended' && u.is_active) return false
    return true
  })

  const hasFilters = search || roleFilter || statusFilter

  return (
    <div className="p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">SuperAdmins</h1>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Super admin access only</p>
        </div>
        <button
          onClick={() => { setForm({ email: '', name: '', password: '', role: 'admin' }); setFormError(null); setShowCreate(true) }}
          className="bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New User
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <input
          type="text"
          placeholder="Search name or email…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 w-56"
        />
        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">All roles</option>
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
        </select>
        {hasFilters && (
          <button
            onClick={() => { setSearch(''); setRoleFilter(''); setStatusFilter('') }}
            className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600"
          >
            Clear filters
          </button>
        )}
        <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">
          {filtered.length} of {users.length}
        </span>
      </div>

      {isLoading ? (
        <div className="text-gray-400 dark:text-gray-500 text-sm">Loading…</div>
      ) : (
        <div className="zr-table-wrap">
          <table className="zr-table min-w-[600px]">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => (
                <tr key={u.id}>
                  <td><EntityIdChip id={u.id} ref={u.ref} /></td>
                  <td className="font-medium">
                    {u.name}
                    {u.id === me?.id && <span className="ml-1 text-xs text-brand-400">(you)</span>}
                  </td>
                  <td className="text-[var(--zr-muted)]">{u.email}</td>
                  <td>
                    <span className="text-xs font-medium text-[var(--zr-muted)]">
                      {ROLES.find((r) => r.value === u.role)?.label ?? u.role}
                    </span>
                  </td>
                  <td>
                    <StatusBadge status={u.is_active ? 'active' : 'suspended'} />
                  </td>
                  <td className="zr-cell-pad">
                    <div className="flex flex-wrap items-center gap-2">
                      <button onClick={() => openEdit(u)} className="text-brand-600 hover:underline text-xs">Edit</button>
                      {u.id !== me?.id && (
                        u.is_active ? (
                          <button onClick={() => suspendMutation.mutate(u.id)} className="text-amber-600 hover:underline text-xs">Suspend</button>
                        ) : (
                          <button onClick={() => activateMutation.mutate(u.id)} className="text-green-600 hover:underline text-xs">Activate</button>
                        )
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={6} className="text-center text-[var(--zr-faint)] py-8">
                  {users.length === 0 ? 'No users yet.' : 'No users match the current filters.'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {editUser && (
        <Modal title={`Edit — ${editUser.name}`} onClose={() => setEditUser(null)}>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              editMutation.mutate({ id: editUser.id, name: editForm.name, role: editForm.role })
            }}
            className="space-y-4"
          >
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
              <input
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                required
                autoFocus
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Role</label>
              <select
                value={editForm.role}
                onChange={(e) => setEditForm({ ...editForm, role: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                {ROLES.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>
            {editError && <p className="text-sm text-red-600">{editError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setEditUser(null)} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800">Cancel</button>
              <button type="submit" disabled={editMutation.isPending} className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg">Save</button>
            </div>
          </form>
        </Modal>
      )}

      {showCreate && (
        <Modal title="New SuperAdmin" onClose={() => setShowCreate(false)}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
                autoFocus
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="Jane Smith"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Email</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="jane@example.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Password (min 12 chars)</label>
              <input
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                required
                minLength={12}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Role</label>
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                {ROLES.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800">Cancel</button>
              <button type="submit" disabled={createMutation.isPending} className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg">Create</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
