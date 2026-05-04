/** Portal Users management page — super_admin only. */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/axios'
import { useAuth } from '../context/AuthContext'
import type { PortalUser } from '../types'
import { EntityIdChip } from '../components/EntityIdChip'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'

async function fetchPortalUsers(): Promise<PortalUser[]> {
  const { data } = await api.get('/portal-users/', { params: { limit: 200 } })
  return data
}

const ROLES = ['super_admin', 'admin', 'reseller'] as const

export function PortalUsersPage() {
  const { user: me } = useAuth()
  const qc = useQueryClient()
  const { data: users = [], isLoading } = useQuery({ queryKey: ['portal-users'], queryFn: fetchPortalUsers })

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ email: '', name: '', password: '', role: 'admin' as string })
  const [formError, setFormError] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['portal-users'] })

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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    createMutation.mutate(form)
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Portal Users</h1>
          <p className="text-xs text-gray-400 mt-0.5">Super admin access only</p>
        </div>
        <button
          onClick={() => { setForm({ email: '', name: '', password: '', role: 'admin' }); setFormError(null); setShowCreate(true) }}
          className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New User
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
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3"><EntityIdChip id={u.id} /></td>
                  <td className="px-4 py-3 font-medium text-gray-900">
                    {u.name}
                    {u.id === me?.id && <span className="ml-1 text-xs text-indigo-400">(you)</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-500">{u.email}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs font-medium text-gray-600 capitalize">{u.role.replace('_', ' ')}</span>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={u.is_active ? 'active' : 'suspended'} />
                  </td>
                  <td className="px-4 py-3 flex gap-2">
                    {/* Cannot suspend yourself */}
                    {u.id !== me?.id && (
                      u.is_active ? (
                        <button onClick={() => suspendMutation.mutate(u.id)} className="text-amber-600 hover:underline text-xs">Suspend</button>
                      ) : (
                        <button onClick={() => activateMutation.mutate(u.id)} className="text-green-600 hover:underline text-xs">Activate</button>
                      )
                    )}
                  </td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-400">No users yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <Modal title="New Portal User" onClose={() => setShowCreate(false)}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
                autoFocus
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Jane Smith"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="jane@example.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Password (min 12 chars)</label>
              <input
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                required
                minLength={12}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>{r.replace('_', ' ')}</option>
                ))}
              </select>
            </div>
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">Cancel</button>
              <button type="submit" className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg">Create</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
