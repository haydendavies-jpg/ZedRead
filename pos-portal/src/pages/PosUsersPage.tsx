/** Admin page for managing POS users — list, create, edit, assign to site, deactivate. */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/axios'
import type { Brand, Site } from '../types'
import { EntityIdChip } from '../components/EntityIdChip'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'

interface SiteGrant {
  grant_id: string
  site_id: string
  site_name: string
  is_default: boolean
  access_profile_name: string
  can_access_portal: boolean
}

interface PosUser {
  id: string
  ref: string
  brand_id: string
  name: string
  email: string
  is_active: boolean
  site_grants: SiteGrant[]
  has_portal_access: boolean
}

interface AccessProfile {
  id: string
  name: string
  can_access_portal: boolean
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

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [siteFilter, setSiteFilter] = useState('')
  const [portalFilter, setPortalFilter] = useState('')

  // ── Create user state ─────────────────────────────────────────────────────
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)

  // ── Edit user state ───────────────────────────────────────────────────────
  const [editUser, setEditUser] = useState<PosUser | null>(null)
  const [editName, setEditName] = useState('')
  const [editEmail, setEditEmail] = useState('')
  const [editError, setEditError] = useState<string | null>(null)

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
    onError: (e: any) => {
      invalidateUsers()
      setCreateError(e?.response?.data?.detail ?? 'Failed to create user.')
    },
  })

  const editMutation = useMutation({
    mutationFn: ({ id, name, email }: { id: string; name: string; email: string }) =>
      api.patch(`/pos-users/${id}`, { name, email }),
    onSuccess: () => {
      invalidateUsers()
      setEditUser(null)
    },
    onError: (e: any) => {
      invalidateUsers()
      setEditError(e?.response?.data?.detail ?? 'Failed to update user.')
    },
  })

  const grantMutation = useMutation({
    mutationFn: (body: { user_id: string; site_id: string; access_profile_id: string }) =>
      api.post('/access-grants', { ...body, scope: 'site' }),
    onSuccess: () => {
      invalidateUsers()
      setGrantUser(null)
    },
    onError: (e: any) =>
      setGrantError(e?.response?.data?.detail ?? 'Failed to create grant.'),
  })

  const deactivateMutation = useMutation({
    mutationFn: (userId: string) => api.patch(`/pos-users/${userId}/deactivate`),
    onSuccess: invalidateUsers,
  })

  const setDefaultMutation = useMutation({
    mutationFn: (grantId: string) => api.post(`/access-grants/${grantId}/set-default`),
    onSuccess: invalidateUsers,
    onError: (e: any) => alert(e?.response?.data?.detail ?? 'Failed to set primary site.'),
  })

  const openCreate = () => {
    setName(''); setEmail(''); setPassword(''); setCreateError(null)
    setShowCreate(true)
  }

  const openEdit = (user: PosUser) => {
    setEditName(user.name)
    setEditEmail(user.email)
    setEditError(null)
    setEditUser(user)
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

  const handleEdit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!editUser) return
    setEditError(null)
    editMutation.mutate({ id: editUser.id, name: editName, email: editEmail })
  }

  const handleGrant = (e: React.FormEvent) => {
    e.preventDefault()
    setGrantError(null)
    if (!grantUser) return
    grantMutation.mutate({ user_id: grantUser.id, site_id: grantSiteId, access_profile_id: grantProfileId })
  }

  const filtered = users.filter((u) => {
    if (search) {
      const q = search.toLowerCase()
      if (!u.name.toLowerCase().includes(q) && !u.email.toLowerCase().includes(q)) return false
    }
    if (statusFilter === 'active' && !u.is_active) return false
    if (statusFilter === 'inactive' && u.is_active) return false
    if (siteFilter && !u.site_grants.some((g) => g.site_name === siteFilter)) return false
    if (portalFilter === 'yes' && !u.has_portal_access) return false
    if (portalFilter === 'no' && u.has_portal_access) return false
    return true
  })

  const hasFilters = search || statusFilter || siteFilter || portalFilter

  return (
    <div className="p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-gray-900">POS Users</h1>
        <button
          onClick={openCreate}
          disabled={!brandId}
          className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New User
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <select
          value={brandId}
          onChange={(e) => { setSelectedBrandId(e.target.value); setSearch(''); setStatusFilter(''); setSiteFilter(''); setPortalFilter('') }}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          {brands.map((b) => (
            <option key={b.id} value={b.id}>{b.name}</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Search name or email…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 w-48"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">Any status</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
        <select
          value={siteFilter}
          onChange={(e) => setSiteFilter(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">Any site</option>
          {brandSites.map((s) => (
            <option key={s.id} value={s.name}>{s.name}</option>
          ))}
        </select>
        <select
          value={portalFilter}
          onChange={(e) => setPortalFilter(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">Any portal access</option>
          <option value="yes">Portal access</option>
          <option value="no">No portal access</option>
        </select>
        {hasFilters && (
          <button
            onClick={() => { setSearch(''); setStatusFilter(''); setSiteFilter(''); setPortalFilter('') }}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            Clear filters
          </button>
        )}
        <span className="text-xs text-gray-400 ml-auto">
          {filtered.length} of {users.length}
        </span>
      </div>

      {isLoading ? (
        <div className="text-gray-400 text-sm">Loading…</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm min-w-[720px]">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Sites</th>
                <th className="px-4 py-3">Portal</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.map((u) => (
                <tr key={u.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3"><EntityIdChip id={u.id} ref={u.ref} /></td>
                  <td className="px-4 py-3 font-medium text-gray-900">{u.name}</td>
                  <td className="px-4 py-3 text-gray-500">{u.email}</td>
                  <td className="px-4 py-3">
                    {u.site_grants.length === 0 ? (
                      <span className="text-xs text-gray-400">None</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {u.site_grants.map((g) => (
                          <span key={g.grant_id} className="inline-flex items-center gap-1">
                            <span className={`inline-block px-2 py-0.5 rounded text-xs ${g.is_default ? 'bg-brand-50 text-brand-700 font-medium' : 'bg-gray-100 text-gray-600'}`}>
                              {g.is_default ? '★ ' : ''}{g.site_name}
                            </span>
                            {!g.is_default && (
                              <button
                                onClick={() => setDefaultMutation.mutate(g.grant_id)}
                                className="text-gray-400 hover:text-brand-600 text-xs"
                                title="Set as primary site"
                              >
                                Set primary
                              </button>
                            )}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {u.has_portal_access ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-brand-50 text-brand-700">Yes</span>
                    ) : (
                      <span className="text-xs text-gray-400">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={u.is_active ? 'active' : 'disabled'} />
                  </td>
                  <td className="px-4 py-3 flex gap-3">
                    <button
                      onClick={() => openEdit(u)}
                      className="text-brand-600 hover:underline text-xs"
                    >
                      Edit
                    </button>
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
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                    {users.length === 0 ? 'No POS users yet. Create one above.' : 'No users match the current filters.'}
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

      {/* ── Edit user modal ───────────────────────────────────────────────── */}
      {editUser && (
        <Modal title={`Edit — ${editUser.name}`} onClose={() => setEditUser(null)}>
          <form onSubmit={handleEdit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                required
                autoFocus
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input
                type="email"
                value={editEmail}
                onChange={(e) => setEditEmail(e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            {editError && <p className="text-sm text-red-600">{editError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setEditUser(null)} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">
                Cancel
              </button>
              <button
                type="submit"
                disabled={editMutation.isPending}
                className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg"
              >
                {editMutation.isPending ? 'Saving…' : 'Save'}
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
              {brandSites.length === 0 ? (
                <p className="text-sm text-gray-500 py-2">No sites found for this brand. Create a site first.</p>
              ) : (
                <select
                  value={grantSiteId}
                  onChange={(e) => setGrantSiteId(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                >
                  <option value="">— Select a site —</option>
                  {brandSites.map((s) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              )}
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
                  <option key={p.id} value={p.id}>
                    {p.name}{p.can_access_portal ? ' · Portal access' : ''}
                  </option>
                ))}
              </select>
              <p className="text-xs text-gray-400 mt-1">Profiles marked "Portal access" allow this user to log in to the management portal.</p>
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
