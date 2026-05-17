/** Admin page for managing POS users — list, create, assign to site, deactivate. */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/axios'
import type { Brand, Site } from '../types'
import { EntityIdChip } from '../components/EntityIdChip'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'

interface PosUser {
  id: string
  brand_id: string
  name: string
  email: string
  is_active: boolean
}

interface AccessProfile {
  id: string
  name: string
}

interface AccessGrant {
  id: string
  user_id: string
  site_id: string
  access_profile_id: string
  is_active: boolean
}

async function fetchBrands(): Promise<Brand[]> {
  const { data } = await api.get('/brands/', { params: { limit: 200 } })
  return data
}

async function fetchSites(): Promise<Site[]> {
  const { data } = await api.get('/sites/', { params: { limit: 200 } })
  return data
}

async function fetchPosUsers(brandId: string): Promise<PosUser[]> {
  if (!brandId) return []
  const { data } = await api.get('/pos-users', { params: { brand_id: brandId, limit: 200 } })
  return data
}

async function fetchProfiles(brandId: string): Promise<AccessProfile[]> {
  if (!brandId) return []
  const { data } = await api.get('/access-profiles', { params: { brand_id: brandId, limit: 200 } })
  return data
}

export function PosUsersPage() {
  const qc = useQueryClient()

  const { data: brands = [] } = useQuery({ queryKey: ['brands'], queryFn: fetchBrands })
  const { data: sites = [] } = useQuery({ queryKey: ['sites'], queryFn: fetchSites })

  const [selectedBrandId, setSelectedBrandId] = useState('')
  const brandId = selectedBrandId || brands[0]?.id || ''

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['pos-users', brandId],
    queryFn: () => fetchPosUsers(brandId),
    enabled: !!brandId,
  })

  const { data: profiles = [] } = useQuery({
    queryKey: ['access-profiles', brandId],
    queryFn: () => fetchProfiles(brandId),
    enabled: !!brandId,
  })

  const brandSites = sites.filter((s) => s.brand_id === brandId)

  // ── Create user state ─────────────────────────────────────────────────────
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)

  // ── Grant state ───────────────────────────────────────────────────────────
  const [grantUser, setGrantUser] = useState<PosUser | null>(null)
  const [grantSiteId, setGrantSiteId] = useState('')
  const [grantProfileId, setGrantProfileId] = useState('')
  const [grantError, setGrantError] = useState<string | null>(null)

  const invalidateUsers = () => qc.invalidateQueries({ queryKey: ['pos-users', brandId] })

  const createMutation = useMutation({
    mutationFn: (body: { brand_id: string; name: string; email: string; password: string }) =>
      api.post('/pos-users', body),
    onSuccess: () => {
      invalidateUsers()
      setShowCreate(false)
      setName(''); setEmail(''); setPassword('')
    },
    onError: (e: any) =>
      setCreateError(e?.response?.data?.detail ?? 'Failed to create user.'),
  })

  const grantMutation = useMutation({
    mutationFn: (body: { user_id: string; site_id: string; access_profile_id: string }) =>
      api.post('/access-grants', { ...body, scope: 'site' }),
    onSuccess: () => { setGrantUser(null) },
    onError: (e: any) =>
      setGrantError(e?.response?.data?.detail ?? 'Failed to create grant.'),
  })

  const deactivateMutation = useMutation({
    mutationFn: (userId: string) => api.patch(`/pos-users/${userId}/deactivate`),
    onSuccess: invalidateUsers,
  })

  const openCreate = () => {
    setName(''); setEmail(''); setPassword(''); setCreateError(null)
    setShowCreate(true)
  }

  const openGrant = (user: PosUser) => {
    setGrantSiteId(brandSites[0]?.id ?? '')
    setGrantProfileId(profiles[0]?.id ?? '')
    setGrantError(null)
    setGrantUser(user)
  }

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    setCreateError(null)
    createMutation.mutate({ brand_id: brandId, name, email, password })
  }

  const handleGrant = (e: React.FormEvent) => {
    e.preventDefault()
    setGrantError(null)
    if (!grantUser) return
    grantMutation.mutate({ user_id: grantUser.id, site_id: grantSiteId, access_profile_id: grantProfileId })
  }

  const activeBrandName = brands.find((b) => b.id === brandId)?.name ?? ''

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">POS Users</h1>
          {activeBrandName && (
            <p className="text-sm text-gray-500 mt-0.5">Brand: {activeBrandName}</p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <select
            value={brandId}
            onChange={(e) => setSelectedBrandId(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            {brands.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
          <button
            onClick={openCreate}
            disabled={!brandId}
            className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            + New User
          </button>
        </div>
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
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3"><EntityIdChip id={u.id} /></td>
                  <td className="px-4 py-3 font-medium text-gray-900">{u.name}</td>
                  <td className="px-4 py-3 text-gray-500">{u.email}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={u.is_active ? 'active' : 'disabled'} />
                  </td>
                  <td className="px-4 py-3 flex gap-3">
                    <button
                      onClick={() => openGrant(u)}
                      className="text-brand-600 hover:underline text-xs"
                    >
                      Assign Site
                    </button>
                    {u.is_active && (
                      <button
                        onClick={() => deactivateMutation.mutate(u.id)}
                        className="text-red-500 hover:underline text-xs"
                      >
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                    No POS users yet. Create one above.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Create user modal ─────────────────────────────────────────────── */}
      {showCreate && (
        <Modal title="New POS User" onClose={() => setShowCreate(false)}>
          <form onSubmit={handleCreate} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                autoFocus
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="Jane Smith"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="jane@example.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="Min 8 characters"
              />
            </div>
            {createError && <p className="text-sm text-red-600">{createError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">
                Cancel
              </button>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg"
              >
                {createMutation.isPending ? 'Creating…' : 'Create'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* ── Assign site modal ─────────────────────────────────────────────── */}
      {grantUser && (
        <Modal title={`Assign Site — ${grantUser.name}`} onClose={() => setGrantUser(null)}>
          <form onSubmit={handleGrant} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Site</label>
              <select
                value={grantSiteId}
                onChange={(e) => setGrantSiteId(e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                {brandSites.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Access Profile</label>
              <select
                value={grantProfileId}
                onChange={(e) => setGrantProfileId(e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            {grantError && <p className="text-sm text-red-600">{grantError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setGrantUser(null)} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">
                Cancel
              </button>
              <button
                type="submit"
                disabled={grantMutation.isPending || !grantSiteId || !grantProfileId}
                className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg"
              >
                {grantMutation.isPending ? 'Assigning…' : 'Assign'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
