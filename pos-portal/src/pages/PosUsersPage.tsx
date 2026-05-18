/** Admin page for managing POS users — list, create, edit (with grants, PIN, backend role). */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/axios'
import type { Brand, Site } from '../types'
import { EntityIdChip } from '../components/EntityIdChip'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'

// ── Types ─────────────────────────────────────────────────────────────────────

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
  brand_name: string
  group_name: string
  name: string
  email: string
  backend_role: string | null
  is_active: boolean
  site_grants: SiteGrant[]
  has_portal_access: boolean
}

interface AccessProfile {
  id: string
  name: string
  can_access_portal: boolean
}

interface Group {
  id: string
  name: string
}

interface EnrichedGrant {
  grant_id: string
  scope: 'site' | 'brand' | 'group'
  site_id: string | null
  site_name: string | null
  brand_id: string | null
  brand_name: string | null
  group_id: string | null
  group_name: string | null
  access_profile_id: string
  access_profile_name: string
  can_access_portal: boolean
  is_default: boolean
  is_active: boolean
}

// ── API helpers ───────────────────────────────────────────────────────────────

async function fetchBrands(): Promise<Brand[]> {
  const { data } = await api.get('/brands/', { params: { limit: 200 } })
  return data
}

async function fetchSites(): Promise<Site[]> {
  const { data } = await api.get('/sites/', { params: { limit: 200 } })
  return data
}

async function fetchGroups(): Promise<Group[]> {
  const { data } = await api.get('/groups/', { params: { limit: 200 } })
  return data
}

async function fetchPosUsers(brandId: string): Promise<PosUser[]> {
  const params: Record<string, unknown> = { limit: 200 }
  if (brandId) params.brand_id = brandId
  const { data } = await api.get('/pos-users', { params })
  return data
}

async function fetchProfiles(brandId: string): Promise<AccessProfile[]> {
  if (!brandId) return []
  const { data } = await api.get('/access-profiles', { params: { brand_id: brandId, limit: 200 } })
  return data
}

async function fetchUserGrants(userId: string): Promise<EnrichedGrant[]> {
  const { data } = await api.get(`/pos-users/${userId}/grants`)
  return data
}

// ── Constants ─────────────────────────────────────────────────────────────────

const BACKEND_ROLES = [
  { value: 'admin', label: 'Admin' },
  { value: 'users', label: 'Users' },
  { value: 'reporting', label: 'Reporting' },
]

const SCOPE_LABELS: Record<string, string> = {
  site: 'Site',
  brand: 'Brand',
  group: 'Group',
}

// ── Component ─────────────────────────────────────────────────────────────────

export function PosUsersPage() {
  const qc = useQueryClient()

  const { data: brands = [] } = useQuery({ queryKey: ['brands'], queryFn: fetchBrands })
  const { data: sites = [] } = useQuery({ queryKey: ['sites'], queryFn: fetchSites })
  const { data: groups = [] } = useQuery({ queryKey: ['groups'], queryFn: fetchGroups })

  const [selectedBrandId, setSelectedBrandId] = useState('')

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['pos-users', selectedBrandId],
    queryFn: () => fetchPosUsers(selectedBrandId),
  })

  const { data: profiles = [] } = useQuery({
    queryKey: ['access-profiles', selectedBrandId],
    queryFn: () => fetchProfiles(selectedBrandId),
    enabled: !!selectedBrandId,
  })

  const brandSites = selectedBrandId ? sites.filter((s) => s.brand_id === selectedBrandId) : sites

  // ── Page-level filters ────────────────────────────────────────────────────
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
  const [editBackendRole, setEditBackendRole] = useState<string>('')
  const [editError, setEditError] = useState<string | null>(null)

  // PIN section within edit modal
  const [pinValue, setPinValue] = useState('')
  const [pinError, setPinError] = useState<string | null>(null)
  const [pinSuccess, setPinSuccess] = useState(false)

  // Grants section within edit modal
  const [grantScopeFilter, setGrantScopeFilter] = useState('')
  const [grantSearch, setGrantSearch] = useState('')

  // Add-grant form within edit modal
  const [addGrantScope, setAddGrantScope] = useState<'site' | 'brand' | 'group'>('site')
  const [addGrantEntityId, setAddGrantEntityId] = useState('')
  const [addGrantProfileId, setAddGrantProfileId] = useState('')
  const [addGrantError, setAddGrantError] = useState<string | null>(null)

  // ── Queries for edit modal ────────────────────────────────────────────────
  const { data: editGrants = [], isLoading: grantsLoading } = useQuery({
    queryKey: ['user-grants', editUser?.id],
    queryFn: () => fetchUserGrants(editUser!.id),
    enabled: !!editUser,
  })

  // Profiles for the edit modal — keyed to the specific user's brand so they
  // always load even when the page-level brand filter is set to "Any".
  const { data: editUserProfiles = [] } = useQuery({
    queryKey: ['access-profiles', editUser?.brand_id],
    queryFn: () => fetchProfiles(editUser!.brand_id),
    enabled: !!editUser,
  })

  const invalidateUsers = () => qc.invalidateQueries({ queryKey: ['pos-users', selectedBrandId] })
  const invalidateGrants = () => qc.invalidateQueries({ queryKey: ['user-grants', editUser?.id] })

  // ── Mutations ─────────────────────────────────────────────────────────────
  const createMutation = useMutation({
    mutationFn: (body: { brand_id: string; name: string; email: string; password: string }) =>
      api.post('/pos-users', body),
    onSuccess: () => {
      invalidateUsers()
      setShowCreate(false)
      setName(''); setEmail(''); setPassword('')
      setCreateError(null)
    },
    onError: (e: any) => {
      invalidateUsers()
      setCreateError(e?.response?.data?.detail ?? 'Failed to create user.')
    },
  })

  const editMutation = useMutation({
    mutationFn: ({ id, name, email, backend_role }: { id: string; name: string; email: string; backend_role: string | null }) =>
      api.patch(`/pos-users/${id}`, { name, email, backend_role }),
    onSuccess: () => {
      invalidateUsers()
      setEditError(null)
    },
    onError: (e: any) => {
      invalidateUsers()
      setEditError(e?.response?.data?.detail ?? 'Failed to update user.')
    },
  })

  const setPinMutation = useMutation({
    mutationFn: ({ userId, pin }: { userId: string; pin: string }) =>
      api.post(`/pos-users/${userId}/set-pin`, { pin }),
    onSuccess: () => {
      setPinError(null)
      setPinSuccess(true)
      setPinValue('')
      setTimeout(() => setPinSuccess(false), 3000)
    },
    onError: (e: any) => {
      setPinError(e?.response?.data?.detail ?? 'Failed to set PIN.')
    },
  })

  const addGrantMutation = useMutation({
    mutationFn: (body: { user_id: string; scope: string; site_id?: string; brand_id?: string; group_id?: string; access_profile_id: string }) =>
      api.post('/access-grants', body),
    onSuccess: () => {
      invalidateUsers()
      invalidateGrants()
      setAddGrantEntityId('')
      setAddGrantError(null)
    },
    onError: (e: any) => {
      invalidateUsers()
      invalidateGrants()
      setAddGrantError(e?.response?.data?.detail ?? 'Failed to add access.')
    },
  })

  const revokeGrantMutation = useMutation({
    mutationFn: (grantId: string) => api.delete(`/access-grants/${grantId}`),
    onSuccess: () => {
      invalidateUsers()
      invalidateGrants()
    },
    onError: (e: any) => alert(e?.response?.data?.detail ?? 'Failed to remove access.'),
  })

  const updateGrantProfileMutation = useMutation({
    mutationFn: ({ grantId, profileId }: { grantId: string; profileId: string }) =>
      api.patch(`/access-grants/${grantId}`, { access_profile_id: profileId }),
    onSuccess: () => {
      invalidateUsers()
      invalidateGrants()
    },
    onError: (e: any) => alert(e?.response?.data?.detail ?? 'Failed to update access profile.'),
  })

  const setDefaultMutation = useMutation({
    mutationFn: (grantId: string) => api.post(`/access-grants/${grantId}/set-default`),
    onSuccess: () => {
      invalidateUsers()
      invalidateGrants()
    },
    onError: (e: any) => alert(e?.response?.data?.detail ?? 'Failed to set primary site.'),
  })

  const deactivateMutation = useMutation({
    mutationFn: (userId: string) => api.patch(`/pos-users/${userId}/deactivate`),
    onSuccess: invalidateUsers,
  })

  // ── Handlers ──────────────────────────────────────────────────────────────
  const openCreate = () => {
    setName(''); setEmail(''); setPassword(''); setCreateError(null)
    setShowCreate(true)
  }

  const openEdit = (user: PosUser) => {
    setEditName(user.name)
    setEditEmail(user.email)
    setEditBackendRole(user.backend_role ?? '')
    setEditError(null)
    setPinValue(''); setPinError(null); setPinSuccess(false)
    setGrantScopeFilter(''); setGrantSearch('')
    setAddGrantScope('site'); setAddGrantEntityId(''); setAddGrantProfileId(''); setAddGrantError(null)
    setEditUser(user)
  }

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    setCreateError(null)
    createMutation.mutate({ brand_id: selectedBrandId, name, email, password })
  }

  const handleEditSave = (e: React.FormEvent) => {
    e.preventDefault()
    if (!editUser) return
    setEditError(null)
    editMutation.mutate({
      id: editUser.id,
      name: editName,
      email: editEmail,
      backend_role: editBackendRole || null,
    })
  }

  const handleSetPin = (e: React.FormEvent) => {
    e.preventDefault()
    if (!editUser) return
    setPinError(null)
    if (!/^\d{4,6}$/.test(pinValue)) {
      setPinError('PIN must be 4–6 digits.')
      return
    }
    setPinMutation.mutate({ userId: editUser.id, pin: pinValue })
  }

  const handleAddGrant = (e: React.FormEvent) => {
    e.preventDefault()
    if (!editUser || !addGrantEntityId || !addGrantProfileId) return
    setAddGrantError(null)
    const body: any = {
      user_id: editUser.id,
      scope: addGrantScope,
      access_profile_id: addGrantProfileId,
    }
    if (addGrantScope === 'site') body.site_id = addGrantEntityId
    else if (addGrantScope === 'brand') body.brand_id = addGrantEntityId
    else body.group_id = addGrantEntityId
    addGrantMutation.mutate(body)
  }

  // ── Filtered data ─────────────────────────────────────────────────────────
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

  const filteredGrants = editGrants.filter((g) => {
    if (grantScopeFilter && g.scope !== grantScopeFilter) return false
    if (grantSearch) {
      const q = grantSearch.toLowerCase()
      const haystack = [g.site_name, g.brand_name, g.group_name].filter(Boolean).join(' ').toLowerCase()
      if (!haystack.includes(q)) return false
    }
    return true
  })

  // Entities available for adding a new grant (exclude already-granted ones)
  const grantedSiteIds = new Set(editGrants.filter((g) => g.scope === 'site').map((g) => g.site_id))
  const grantedBrandIds = new Set(editGrants.filter((g) => g.scope === 'brand').map((g) => g.brand_id))
  const grantedGroupIds = new Set(editGrants.filter((g) => g.scope === 'group').map((g) => g.group_id))

  const availableSites = brandSites.filter((s) => !grantedSiteIds.has(s.id))
  const availableBrands = brands.filter((b) => !grantedBrandIds.has(b.id))
  const availableGroups = groups.filter((g) => !grantedGroupIds.has(g.id))

  const entityOptions =
    addGrantScope === 'site' ? availableSites :
    addGrantScope === 'brand' ? availableBrands :
    availableGroups

  // profilesForEdit is used inside the edit modal — always sourced from the
  // edit user's own brand, regardless of the page-level brand filter.
  const profilesForEdit = editUserProfiles

  return (
    <div className="p-4 sm:p-6">
      {/* ── Page header ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-gray-900">POS Users</h1>
        <button
          onClick={openCreate}
          disabled={!selectedBrandId}
          title={!selectedBrandId ? 'Select a brand first' : undefined}
          className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New User
        </button>
      </div>

      {/* ── Page-level filters (labels above controls) ───────────────────── */}
      <div className="flex flex-wrap items-end gap-3 mb-4">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">Brand</label>
          <select
            value={selectedBrandId}
            onChange={(e) => { setSelectedBrandId(e.target.value); setSearch(''); setStatusFilter(''); setSiteFilter(''); setPortalFilter('') }}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="">Any</option>
            {brands.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">Search</label>
          <input
            type="text"
            placeholder="Name or email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 w-40"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">Status</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="">Any</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">Site</label>
          <select
            value={siteFilter}
            onChange={(e) => setSiteFilter(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="">Any</option>
            {brandSites.map((s) => (
              <option key={s.id} value={s.name}>{s.name}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">Portal</label>
          <select
            value={portalFilter}
            onChange={(e) => setPortalFilter(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="">Any</option>
            <option value="yes">Has access</option>
            <option value="no">No access</option>
          </select>
        </div>

        {hasFilters && (
          <button
            onClick={() => { setSearch(''); setStatusFilter(''); setSiteFilter(''); setPortalFilter('') }}
            className="text-xs text-gray-400 hover:text-gray-600 self-end pb-1.5"
          >
            Clear filters
          </button>
        )}
        <span className="text-xs text-gray-400 ml-auto self-end pb-1.5">
          {filtered.length} of {users.length}
        </span>
      </div>

      {/* ── Users table ──────────────────────────────────────────────────────── */}
      {isLoading ? (
        <div className="text-gray-400 text-sm">Loading…</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm min-w-[900px]">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Group</th>
                <th className="px-4 py-3">Brand</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Sites</th>
                <th className="px-4 py-3">Backend</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.map((u) => (
                <tr key={u.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3"><EntityIdChip id={u.id} ref={u.ref} /></td>
                  <td className="px-4 py-3 text-gray-500">{u.group_name || <span className="text-gray-300">—</span>}</td>
                  <td className="px-4 py-3 text-gray-700">{u.brand_name || <span className="text-gray-300">—</span>}</td>
                  <td className="px-4 py-3 font-medium text-gray-900">{u.name}</td>
                  <td className="px-4 py-3 text-gray-500">{u.email}</td>
                  <td className="px-4 py-3">
                    {u.site_grants.length === 0 ? (
                      <span className="text-xs text-gray-400">None</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {u.site_grants.map((g) => (
                          <span
                            key={g.grant_id}
                            className={`inline-block px-2 py-0.5 rounded text-xs ${g.is_default ? 'bg-brand-50 text-brand-700 font-medium' : 'bg-gray-100 text-gray-600'}`}
                          >
                            {g.is_default ? '★ ' : ''}{g.site_name}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {u.backend_role ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700 capitalize">
                        {u.backend_role}
                      </span>
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
                  <td colSpan={9} className="px-4 py-8 text-center text-gray-400">
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

      {/* ── Edit user modal (wide — includes PIN, backend role, grants) ─────── */}
      {editUser && (
        <Modal title={`Edit — ${editUser.name}`} onClose={() => setEditUser(null)} wide>
          <div className="space-y-6">

            {/* ── Section 1: User details ──────────────────────────────────── */}
            <section>
              <h3 className="text-sm font-semibold text-gray-700 mb-3">User Details</h3>
              <form onSubmit={handleEditSave} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                    <input
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      required
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
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Backend Access Level</label>
                  <select
                    value={editBackendRole}
                    onChange={(e) => setEditBackendRole(e.target.value)}
                    className="w-full sm:w-48 px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  >
                    <option value="">No backend access</option>
                    {BACKEND_ROLES.map((r) => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                  <p className="text-xs text-gray-400 mt-1">Controls access to this management portal.</p>
                </div>

                {editError && <p className="text-sm text-red-600">{editError}</p>}
                <div className="flex justify-end">
                  <button
                    type="submit"
                    disabled={editMutation.isPending}
                    className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg"
                  >
                    {editMutation.isPending ? 'Saving…' : 'Save Details'}
                  </button>
                </div>
              </form>
            </section>

            <hr className="border-gray-100" />

            {/* ── Section 2: POS PIN ───────────────────────────────────────── */}
            <section>
              <h3 className="text-sm font-semibold text-gray-700 mb-1">POS PIN</h3>
              <p className="text-xs text-gray-400 mb-3">Set a PIN so the user can quickly switch sessions on the Android terminal without a full re-login.</p>
              <form onSubmit={handleSetPin} className="flex items-end gap-3">
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-gray-500">PIN (4–6 digits)</label>
                  <input
                    type="password"
                    inputMode="numeric"
                    pattern="\d{4,6}"
                    value={pinValue}
                    onChange={(e) => { setPinValue(e.target.value); setPinError(null); setPinSuccess(false) }}
                    placeholder="••••"
                    maxLength={6}
                    className="w-32 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                </div>
                <button
                  type="submit"
                  disabled={setPinMutation.isPending || !pinValue}
                  className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg"
                >
                  {setPinMutation.isPending ? 'Setting…' : 'Set PIN'}
                </button>
                {pinSuccess && <span className="text-xs text-green-600">PIN set successfully.</span>}
              </form>
              {pinError && <p className="text-sm text-red-600 mt-2">{pinError}</p>}
            </section>

            <hr className="border-gray-100" />

            {/* ── Section 3: Access grants ─────────────────────────────────── */}
            <section>
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Site &amp; Scope Access</h3>

              {/* Grant filters */}
              <div className="flex flex-wrap items-end gap-3 mb-3">
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-gray-500">Scope</label>
                  <select
                    value={grantScopeFilter}
                    onChange={(e) => setGrantScopeFilter(e.target.value)}
                    className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  >
                    <option value="">All scopes</option>
                    <option value="site">Site</option>
                    <option value="brand">Brand</option>
                    <option value="group">Group</option>
                  </select>
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-gray-500">Search</label>
                  <input
                    type="text"
                    placeholder="Group, brand, or site…"
                    value={grantSearch}
                    onChange={(e) => setGrantSearch(e.target.value)}
                    className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 w-44"
                  />
                </div>
                {(grantScopeFilter || grantSearch) && (
                  <button
                    onClick={() => { setGrantScopeFilter(''); setGrantSearch('') }}
                    className="text-xs text-gray-400 hover:text-gray-600 self-end pb-1.5"
                  >
                    Clear
                  </button>
                )}
                <span className="text-xs text-gray-400 ml-auto self-end pb-1.5">
                  {filteredGrants.length} of {editGrants.length}
                </span>
              </div>

              {/* Grants table */}
              <div className="overflow-x-auto rounded-lg border border-gray-200 mb-4">
                <table className="w-full text-sm min-w-[620px]">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      <th className="px-3 py-2">Scope</th>
                      <th className="px-3 py-2">Group</th>
                      <th className="px-3 py-2">Brand</th>
                      <th className="px-3 py-2">Site</th>
                      <th className="px-3 py-2">POS Access</th>
                      <th className="px-3 py-2">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {grantsLoading ? (
                      <tr><td colSpan={6} className="px-3 py-4 text-center text-gray-400 text-xs">Loading…</td></tr>
                    ) : filteredGrants.length === 0 ? (
                      <tr><td colSpan={6} className="px-3 py-4 text-center text-gray-400 text-xs">
                        {editGrants.length === 0 ? 'No access grants yet. Add one below.' : 'No grants match the filters.'}
                      </td></tr>
                    ) : filteredGrants.map((g) => (
                      <tr key={g.grant_id} className="hover:bg-gray-50">
                        <td className="px-3 py-2">
                          <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${
                            g.scope === 'group' ? 'bg-purple-50 text-purple-700' :
                            g.scope === 'brand' ? 'bg-blue-50 text-blue-700' :
                            'bg-gray-100 text-gray-600'
                          }`}>
                            {SCOPE_LABELS[g.scope]}
                          </span>
                          {g.scope === 'site' && g.is_default && (
                            <span className="ml-1 text-xs text-brand-600 font-medium">★ Primary</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-gray-500 text-xs">{g.group_name ?? '—'}</td>
                        <td className="px-3 py-2 text-gray-600 text-xs">{g.brand_name ?? '—'}</td>
                        <td className="px-3 py-2 text-gray-700 text-xs">{g.site_name ?? '—'}</td>
                        <td className="px-3 py-2">
                          <select
                            value={g.access_profile_id}
                            onChange={(e) => updateGrantProfileMutation.mutate({ grantId: g.grant_id, profileId: e.target.value })}
                            className="px-2 py-1 border border-gray-200 rounded text-xs text-gray-700 focus:outline-none focus:ring-1 focus:ring-brand-500"
                          >
                            {profilesForEdit.map((p) => (
                              <option key={p.id} value={p.id}>{p.name}</option>
                            ))}
                            {/* Fallback in case loaded profiles don't include the current one */}
                            {!profilesForEdit.find((p) => p.id === g.access_profile_id) && (
                              <option value={g.access_profile_id}>{g.access_profile_name}</option>
                            )}
                          </select>
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-2">
                            {g.scope === 'site' && !g.is_default && (
                              <button
                                onClick={() => setDefaultMutation.mutate(g.grant_id)}
                                className="text-xs text-gray-400 hover:text-brand-600"
                                title="Set as primary site"
                              >
                                Set primary
                              </button>
                            )}
                            <button
                              onClick={() => revokeGrantMutation.mutate(g.grant_id)}
                              className="text-xs text-red-500 hover:underline"
                            >
                              Remove
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Add grant form */}
              <div className="border border-gray-200 rounded-lg p-3 bg-gray-50">
                <p className="text-xs font-medium text-gray-600 mb-3">Add Access</p>
                <form onSubmit={handleAddGrant} className="flex flex-wrap items-end gap-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-gray-500">Scope</label>
                    <select
                      value={addGrantScope}
                      onChange={(e) => { setAddGrantScope(e.target.value as 'site' | 'brand' | 'group'); setAddGrantEntityId('') }}
                      className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500"
                    >
                      <option value="site">Site</option>
                      <option value="brand">Brand</option>
                      <option value="group">Group</option>
                    </select>
                  </div>

                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-gray-500">
                      {addGrantScope === 'site' ? 'Site' : addGrantScope === 'brand' ? 'Brand' : 'Group'}
                    </label>
                    <select
                      value={addGrantEntityId}
                      onChange={(e) => setAddGrantEntityId(e.target.value)}
                      required
                      className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500 min-w-[140px]"
                    >
                      <option value="">— Select —</option>
                      {entityOptions.map((e) => (
                        <option key={e.id} value={e.id}>{e.name}</option>
                      ))}
                    </select>
                  </div>

                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-gray-500">POS Access</label>
                    <select
                      value={addGrantProfileId}
                      onChange={(e) => setAddGrantProfileId(e.target.value)}
                      required
                      className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500"
                    >
                      <option value="">— Profile —</option>
                      {editUserProfiles.map((p) => (
                        <option key={p.id} value={p.id}>{p.name}{p.can_access_portal ? ' · Portal' : ''}</option>
                      ))}
                    </select>
                  </div>

                  <button
                    type="submit"
                    disabled={addGrantMutation.isPending || !addGrantEntityId || !addGrantProfileId}
                    className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-1.5 rounded-lg self-end"
                  >
                    {addGrantMutation.isPending ? 'Adding…' : 'Add'}
                  </button>
                </form>
                {addGrantError && <p className="text-sm text-red-600 mt-2">{addGrantError}</p>}
              </div>
            </section>

            {/* ── Footer close ─────────────────────────────────────────────── */}
            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setEditUser(null)}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
              >
                Close
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
