/** Admin page for managing Users — list, create, edit (with grants, PIN, backend role). */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/axios'
import type { Brand, Site } from '../types'
import { EntityIdChip } from '../components/EntityIdChip'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'
import { apiErrorMessage } from '../utils/apiError'

// ── Types ─────────────────────────────────────────────────────────────────────

interface SiteGrant {
  grant_id: string
  site_id: string
  site_name: string
  is_default: boolean
  access_profile_name: string
  can_access_portal: boolean
}

interface AppUser {
  id: string
  ref: string
  brand_id: string | null
  brand_name: string
  group_name: string
  name: string
  /** Null for Master Users, whose `name` is the site's name rather than a person's. */
  first_name: string | null
  last_name: string | null
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

interface GroupScopeEntry {
  scope: 'group' | 'brand' | 'site'
  brand_id: string | null
  brand_name: string | null
  site_id: string | null
  site_name: string | null
  grant_id: string | null
  access_profile_id: string | null
  access_profile_name: string | null
  can_access_portal: boolean
  is_default: boolean
  backend_role: string | null
}

interface GroupAccess {
  group_id: string
  group_name: string
  entries: GroupScopeEntry[]
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

async function fetchUsers(brandId: string): Promise<AppUser[]> {
  const params: Record<string, unknown> = { limit: 200 }
  if (brandId) params.brand_id = brandId
  const { data } = await api.get('/users', { params })
  return data
}

async function fetchProfiles(brandId: string | null): Promise<AccessProfile[]> {
  if (!brandId) return []
  const { data } = await api.get('/access-profiles', { params: { brand_id: brandId, limit: 200 } })
  return data
}

async function fetchGroupAccess(userId: string): Promise<GroupAccess> {
  const { data } = await api.get(`/users/${userId}/group-access`)
  return data
}

// ── Constants ─────────────────────────────────────────────────────────────────

const BACKEND_ROLES = [
  { value: 'admin', label: 'Admin' },
  { value: 'users', label: 'Users' },
  { value: 'reporting', label: 'Reporting' },
]

// ── Component ─────────────────────────────────────────────────────────────────

export function UsersPage() {
  const qc = useQueryClient()

  const { data: brands = [] } = useQuery({ queryKey: ['brands'], queryFn: fetchBrands })
  const { data: sites = [] } = useQuery({ queryKey: ['sites'], queryFn: fetchSites })

  const [selectedBrandId, setSelectedBrandId] = useState('')

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['users', selectedBrandId],
    queryFn: () => fetchUsers(selectedBrandId),
  })

  const brandSites = selectedBrandId ? sites.filter((s) => s.brand_id === selectedBrandId) : sites

  // ── Page-level filters ────────────────────────────────────────────────────
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [siteFilter, setSiteFilter] = useState('')
  const [portalFilter, setPortalFilter] = useState('')

  // ── Create user state ─────────────────────────────────────────────────────
  const [showCreate, setShowCreate] = useState(false)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)

  // ── Edit user state ───────────────────────────────────────────────────────
  const [editUser, setEditUser] = useState<AppUser | null>(null)
  const [editFirstName, setEditFirstName] = useState('')
  const [editLastName, setEditLastName] = useState('')
  const [editEmail, setEditEmail] = useState('')
  const [editError, setEditError] = useState<string | null>(null)

  // PIN section
  const [pinValue, setPinValue] = useState('')
  const [pinError, setPinError] = useState<string | null>(null)
  const [pinSuccess, setPinSuccess] = useState(false)

  // Access table search
  const [accessSearch, setAccessSearch] = useState('')

  // ── Queries for edit modal ────────────────────────────────────────────────
  const { data: groupAccess, isLoading: accessLoading } = useQuery({
    queryKey: ['group-access', editUser?.id],
    queryFn: () => fetchGroupAccess(editUser!.id),
    enabled: !!editUser,
  })

  // Profiles for the edit modal — keyed to the specific user's brand
  const { data: editUserProfiles = [] } = useQuery({
    queryKey: ['access-profiles', editUser?.brand_id],
    queryFn: () => fetchProfiles(editUser!.brand_id),
    enabled: !!editUser,
  })

  const invalidateUsers = () => qc.invalidateQueries({ queryKey: ['users', selectedBrandId] })
  const invalidateAccess = () => qc.invalidateQueries({ queryKey: ['group-access', editUser?.id] })

  // ── Mutations ─────────────────────────────────────────────────────────────
  const createMutation = useMutation({
    mutationFn: (body: { brand_id: string; first_name: string; last_name: string; email: string; password: string }) =>
      api.post('/users', body),
    onSuccess: () => {
      invalidateUsers()
      setShowCreate(false)
      setFirstName(''); setLastName(''); setEmail(''); setPassword('')
      setCreateError(null)
    },
    onError: (e: unknown) => {
      invalidateUsers()
      setCreateError(apiErrorMessage(e, 'Failed to create user.'))
    },
  })

  const editMutation = useMutation({
    mutationFn: ({ id, firstName, lastName, email }: { id: string; firstName: string; lastName: string; email: string }) =>
      api.patch(`/users/${id}`, { first_name: firstName, last_name: lastName, email }),
    onSuccess: () => {
      invalidateUsers()
      setEditError(null)
    },
    onError: (e: unknown) => {
      invalidateUsers()
      setEditError(apiErrorMessage(e, 'Failed to update user.'))
    },
  })

  const setPinMutation = useMutation({
    mutationFn: ({ userId, pin }: { userId: string; pin: string }) =>
      api.post(`/users/${userId}/set-pin`, { pin }),
    onSuccess: () => {
      setPinError(null)
      setPinSuccess(true)
      setPinValue('')
      setTimeout(() => setPinSuccess(false), 3000)
    },
    onError: (e: unknown) => {
      setPinError(apiErrorMessage(e, 'Failed to set PIN.'))
    },
  })

  const addGrantMutation = useMutation({
    mutationFn: (body: { user_id: string; scope: string; site_id?: string; brand_id?: string; access_profile_id: string }) =>
      api.post('/access-grants', body),
    onSuccess: () => { invalidateUsers(); invalidateAccess() },
    onError: (e: unknown) => {
      invalidateUsers(); invalidateAccess()
      // 409 = grant already exists and was auto-created; just refetch, no alert needed
      if ((e as { response?: { status?: number } })?.response?.status !== 409) {
        alert(apiErrorMessage(e, 'Failed to assign access.'))
      }
    },
  })

  const revokeGrantMutation = useMutation({
    mutationFn: (grantId: string) => api.delete(`/access-grants/${grantId}`),
    onSuccess: () => { invalidateUsers(); invalidateAccess() },
    onError: (e: unknown) => { invalidateUsers(); invalidateAccess(); alert(apiErrorMessage(e, 'Failed to remove access.')) },
  })

  const updateGrantProfileMutation = useMutation({
    mutationFn: ({ grantId, profileId }: { grantId: string; profileId: string }) =>
      api.patch(`/access-grants/${grantId}`, { access_profile_id: profileId }),
    onSuccess: () => { invalidateUsers(); invalidateAccess() },
    onError: (e: unknown) => { invalidateUsers(); invalidateAccess(); alert(apiErrorMessage(e, 'Failed to update access.')) },
  })

  const updateGrantBackendRoleMutation = useMutation({
    mutationFn: ({ grantId, backendRole }: { grantId: string; backendRole: string | null }) =>
      api.patch(`/access-grants/${grantId}`, { backend_role: backendRole }),
    onSuccess: () => { invalidateUsers(); invalidateAccess() },
    onError: (e: unknown) => { invalidateUsers(); invalidateAccess(); alert(apiErrorMessage(e, 'Failed to update backend access.')) },
  })

  const setDefaultMutation = useMutation({
    mutationFn: (grantId: string) => api.post(`/access-grants/${grantId}/set-default`),
    onSuccess: () => { invalidateUsers(); invalidateAccess() },
    onError: (e: unknown) => alert(apiErrorMessage(e, 'Failed to set primary site.')),
  })

  const deactivateMutation = useMutation({
    mutationFn: (userId: string) => api.patch(`/users/${userId}/deactivate`),
    onSuccess: invalidateUsers,
  })

  // ── Handlers ──────────────────────────────────────────────────────────────
  const openCreate = () => {
    setFirstName(''); setLastName(''); setEmail(''); setPassword(''); setCreateError(null)
    setShowCreate(true)
  }

  const openEdit = (user: AppUser) => {
    // Older rows created before the Stage 15 first/last split carry only a
    // composed `name` — fall back to splitting it on the first space.
    setEditFirstName(user.first_name ?? user.name.split(' ')[0] ?? '')
    setEditLastName(user.last_name ?? user.name.split(' ').slice(1).join(' '))
    setEditEmail(user.email)
    setEditError(null)
    setPinValue(''); setPinError(null); setPinSuccess(false)
    setAccessSearch('')
    setEditUser(user)
  }

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    setCreateError(null)
    createMutation.mutate({ brand_id: selectedBrandId, first_name: firstName, last_name: lastName, email, password })
  }

  const handleEditSave = (e: React.FormEvent) => {
    e.preventDefault()
    if (!editUser) return
    setEditError(null)
    editMutation.mutate({ id: editUser.id, firstName: editFirstName, lastName: editLastName, email: editEmail })
  }

  const handleSetPin = (e: React.FormEvent) => {
    e.preventDefault()
    if (!editUser) return
    setPinError(null)
    if (!/^\d{4,6}$/.test(pinValue)) { setPinError('PIN must be 4–6 digits.'); return }
    setPinMutation.mutate({ userId: editUser.id, pin: pinValue })
  }

  /** Called when the POS access dropdown changes for a brand or site row. */
  const handleAccessChange = (entry: GroupScopeEntry, newProfileId: string) => {
    if (!editUser) return
    if (!newProfileId && entry.grant_id) {
      revokeGrantMutation.mutate(entry.grant_id)
    } else if (newProfileId && !entry.grant_id) {
      const body: { user_id: string; scope: string; site_id?: string; brand_id?: string; access_profile_id: string } = {
        user_id: editUser.id, scope: entry.scope, access_profile_id: newProfileId,
      }
      if (entry.scope === 'site') body.site_id = entry.site_id ?? undefined
      else body.brand_id = entry.brand_id ?? undefined
      addGrantMutation.mutate(body)
    } else if (newProfileId && entry.grant_id && newProfileId !== entry.access_profile_id) {
      updateGrantProfileMutation.mutate({ grantId: entry.grant_id, profileId: newProfileId })
    }
  }

  /** Called when the Backend Access dropdown changes for any row. */
  const handleBackendRoleChange = (entry: GroupScopeEntry, newRole: string) => {
    if (!editUser || !entry.grant_id) return
    updateGrantBackendRoleMutation.mutate({ grantId: entry.grant_id, backendRole: newRole || null })
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

  const filteredEntries = (groupAccess?.entries ?? []).filter((e) => {
    if (e.scope === 'group') return true  // group row always visible
    if (!accessSearch) return true
    const q = accessSearch.toLowerCase()
    return (e.brand_name?.toLowerCase().includes(q) || e.site_name?.toLowerCase().includes(q))
  })

  return (
    <div className="p-4 sm:p-6">
      {/* ── Page header ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Users</h1>
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
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Brand</label>
          <select
            value={selectedBrandId}
            onChange={(e) => { setSelectedBrandId(e.target.value); setSearch(''); setStatusFilter(''); setSiteFilter(''); setPortalFilter('') }}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="">Any</option>
            {brands.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Search</label>
          <input
            type="text"
            placeholder="Name or email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 w-40"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Status</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="">Any</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Site</label>
          <select
            value={siteFilter}
            onChange={(e) => setSiteFilter(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="">Any</option>
            {brandSites.map((s) => (
              <option key={s.id} value={s.name}>{s.name}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Portal</label>
          <select
            value={portalFilter}
            onChange={(e) => setPortalFilter(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="">Any</option>
            <option value="yes">Has access</option>
            <option value="no">No access</option>
          </select>
        </div>

        {hasFilters && (
          <button
            onClick={() => { setSearch(''); setStatusFilter(''); setSiteFilter(''); setPortalFilter('') }}
            className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 self-end pb-1.5"
          >
            Clear filters
          </button>
        )}
        <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto self-end pb-1.5">
          {filtered.length} of {users.length}
        </span>
      </div>

      {/* ── Users table ──────────────────────────────────────────────────────── */}
      {isLoading ? (
        <div className="text-gray-400 dark:text-gray-500 text-sm">Loading…</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700">
          <table className="w-full text-sm min-w-[900px]">
            <thead>
              <tr className="border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
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
                <tr key={u.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/60">
                  <td className="px-4 py-3"><EntityIdChip id={u.id} ref={u.ref} /></td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{u.group_name || <span className="text-gray-300">—</span>}</td>
                  <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{u.brand_name || <span className="text-gray-300">—</span>}</td>
                  <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{u.name}</td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{u.email}</td>
                  <td className="px-4 py-3">
                    {u.site_grants.length === 0 ? (
                      <span className="text-xs text-gray-400 dark:text-gray-500">None</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {u.site_grants.map((g) => (
                          <span
                            key={g.grant_id}
                            className={`inline-block px-2 py-0.5 rounded text-xs ${g.is_default ? 'bg-brand-50 text-brand-700 font-medium' : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'}`}
                          >
                            {g.is_default ? '★ ' : ''}{g.site_name}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {u.backend_role ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 capitalize">
                        {u.backend_role}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-400 dark:text-gray-500">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={u.is_active ? 'active' : 'disabled'} />
                  </td>
                  <td className="px-4 py-3 flex gap-3">
                    <button onClick={() => openEdit(u)} className="text-brand-600 hover:underline text-xs">Edit</button>
                    {u.is_active && (
                      <button onClick={() => deactivateMutation.mutate(u.id)} className="text-red-500 hover:underline text-xs">
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-gray-400 dark:text-gray-500">
                    {users.length === 0 ? 'No users yet. Create one above.' : 'No users match the current filters.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Create user modal ─────────────────────────────────────────────── */}
      {showCreate && (
        <Modal title="New User" onClose={() => setShowCreate(false)}>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">First name</label>
                <input value={firstName} onChange={(e) => setFirstName(e.target.value)} required autoFocus
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="Jane" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Last name</label>
                <input value={lastName} onChange={(e) => setLastName(e.target.value)} required
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="Smith" />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Email</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="jane@example.com" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Password</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="Min 8 characters" />
            </div>
            {createError && <p className="text-sm text-red-600">{createError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800">Cancel</button>
              <button type="submit" disabled={createMutation.isPending}
                className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg">
                {createMutation.isPending ? 'Creating…' : 'Create'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* ── Edit user modal ───────────────────────────────────────────────── */}
      {editUser && (
        <Modal title={`Edit — ${editUser.name}`} onClose={() => setEditUser(null)} wide>
          <div className="space-y-6">

            {/* ── Section 1: User details ────────────────────────────────── */}
            <section>
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">User Details</h3>
              <form onSubmit={handleEditSave} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">First name</label>
                    <input value={editFirstName} onChange={(e) => setEditFirstName(e.target.value)} required
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Last name</label>
                    <input value={editLastName} onChange={(e) => setEditLastName(e.target.value)} required
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Email</label>
                    <input type="email" value={editEmail} onChange={(e) => setEditEmail(e.target.value)} required
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
                  </div>
                </div>
                {editError && <p className="text-sm text-red-600">{editError}</p>}
                <div className="flex justify-end">
                  <button type="submit" disabled={editMutation.isPending}
                    className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg">
                    {editMutation.isPending ? 'Saving…' : 'Save Details'}
                  </button>
                </div>
              </form>
            </section>

            <hr className="border-gray-100 dark:border-gray-800" />

            {/* ── Section 2: POS PIN ─────────────────────────────────────── */}
            <section>
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">POS PIN</h3>
              <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">Set a PIN so the user can quickly switch sessions on the Android terminal without a full re-login.</p>
              <form onSubmit={handleSetPin} className="flex items-end gap-3">
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-gray-500 dark:text-gray-400">PIN (4–6 digits)</label>
                  <input type="password" inputMode="numeric" pattern="\d{4,6}" value={pinValue}
                    onChange={(e) => { setPinValue(e.target.value); setPinError(null); setPinSuccess(false) }}
                    placeholder="••••" maxLength={6}
                    className="w-32 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
                </div>
                <button type="submit" disabled={setPinMutation.isPending || !pinValue}
                  className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg">
                  {setPinMutation.isPending ? 'Setting…' : 'Set PIN'}
                </button>
                {pinSuccess && <span className="text-xs text-green-600">PIN set successfully.</span>}
              </form>
              {pinError && <p className="text-sm text-red-600 mt-2">{pinError}</p>}
            </section>

            <hr className="border-gray-100 dark:border-gray-800" />

            {/* ── Section 3: Site & Scope Access ────────────────────────── */}
            <section>
              <div className="flex flex-wrap items-end justify-between gap-3 mb-3">
                <div>
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Site &amp; Scope Access</h3>
                  {groupAccess && (
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Group: <span className="font-medium text-gray-600 dark:text-gray-400">{groupAccess.group_name}</span></p>
                  )}
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Search</label>
                  <input
                    type="text"
                    placeholder="Brand or site…"
                    value={accessSearch}
                    onChange={(e) => setAccessSearch(e.target.value)}
                    className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 w-44"
                  />
                </div>
              </div>

              <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
                <table className="w-full text-sm min-w-[680px]">
                  <thead>
                    <tr className="border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                      <th className="px-3 py-2">Brand</th>
                      <th className="px-3 py-2">Site</th>
                      <th className="px-3 py-2">POS Access</th>
                      <th className="px-3 py-2">Backend Access</th>
                      <th className="px-3 py-2"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {accessLoading ? (
                      <tr><td colSpan={5} className="px-3 py-4 text-center text-gray-400 dark:text-gray-500 text-xs">Loading…</td></tr>
                    ) : filteredEntries.length === 0 ? (
                      <tr><td colSpan={5} className="px-3 py-4 text-center text-gray-400 dark:text-gray-500 text-xs">
                        {(groupAccess?.entries ?? []).length === 0 ? 'No brands or sites found in this group.' : 'No results match the search.'}
                      </td></tr>
                    ) : filteredEntries.map((entry) => {
                      const rowKey = entry.scope === 'group'
                        ? 'group'
                        : `${entry.scope}-${entry.site_id ?? entry.brand_id}`

                      if (entry.scope === 'group') {
                        return (
                          <tr key={rowKey} className="bg-brand-50/40 border-b border-gray-200 dark:border-gray-700">
                            <td className="px-3 py-2 text-xs font-semibold text-brand-800" colSpan={2}>
                              {groupAccess?.group_name ?? 'Group'} <span className="font-normal text-gray-400 dark:text-gray-500">(group-level)</span>
                            </td>
                            <td className="px-3 py-2 text-xs text-gray-400 dark:text-gray-500">—</td>
                            <td className="px-3 py-2">
                              {entry.grant_id ? (
                                <select
                                  value={entry.backend_role ?? ''}
                                  onChange={(e) => handleBackendRoleChange(entry, e.target.value)}
                                  className={`px-2 py-1 border rounded text-xs focus:outline-none focus:ring-1 focus:ring-brand-500 ${entry.backend_role ? 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300' : 'border-gray-200 dark:border-gray-700 text-gray-400 dark:text-gray-500'}`}
                                >
                                  <option value="">No access</option>
                                  {BACKEND_ROLES.map((r) => (
                                    <option key={r.value} value={r.value}>{r.label}</option>
                                  ))}
                                </select>
                              ) : (
                                <span className="text-xs text-gray-400 dark:text-gray-500">Assign a site first</span>
                              )}
                            </td>
                            <td className="px-3 py-2" />
                          </tr>
                        )
                      }

                      return (
                        <tr key={rowKey}
                          className={`hover:bg-gray-50 dark:hover:bg-gray-800/60 ${entry.scope === 'site' ? 'bg-white dark:bg-gray-800' : 'bg-gray-50 dark:bg-gray-900/60'}`}>
                          <td className="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">
                            {entry.scope === 'brand' ? (
                              <span className="font-medium">{entry.brand_name}</span>
                            ) : (
                              <span className="text-gray-400 dark:text-gray-500 pl-3">↳ {entry.brand_name}</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">
                            {entry.site_name ?? <span className="text-gray-400 dark:text-gray-500 italic">All sites</span>}
                          </td>
                          <td className="px-3 py-2">
                            <select
                              value={entry.access_profile_id ?? ''}
                              onChange={(e) => handleAccessChange(entry, e.target.value)}
                              className={`px-2 py-1 border rounded text-xs focus:outline-none focus:ring-1 focus:ring-brand-500 ${
                                entry.access_profile_id ? 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300' : 'border-gray-200 dark:border-gray-700 text-gray-400 dark:text-gray-500'
                              }`}
                            >
                              <option value="">No access</option>
                              {editUserProfiles.map((p) => (
                                <option key={p.id} value={p.id}>{p.name}{p.can_access_portal ? ' · Portal' : ''}</option>
                              ))}
                            </select>
                          </td>
                          <td className="px-3 py-2">
                            {entry.grant_id ? (
                              <select
                                value={entry.backend_role ?? ''}
                                onChange={(e) => handleBackendRoleChange(entry, e.target.value)}
                                className={`px-2 py-1 border rounded text-xs focus:outline-none focus:ring-1 focus:ring-brand-500 ${entry.backend_role ? 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300' : 'border-gray-200 dark:border-gray-700 text-gray-400 dark:text-gray-500'}`}
                              >
                                <option value="">No access</option>
                                {BACKEND_ROLES.map((r) => (
                                  <option key={r.value} value={r.value}>{r.label}</option>
                                ))}
                              </select>
                            ) : (
                              <span className="text-xs text-gray-400 dark:text-gray-500">—</span>
                            )}
                          </td>
                          <td className="px-3 py-2">
                            {entry.scope === 'site' && entry.grant_id && (
                              entry.is_default ? (
                                <span className="text-xs text-brand-600 font-medium">★ Primary</span>
                              ) : (
                                <button
                                  onClick={() => setDefaultMutation.mutate(entry.grant_id!)}
                                  className="text-xs text-gray-400 dark:text-gray-500 hover:text-brand-600"
                                >
                                  Set primary
                                </button>
                              )
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            <div className="flex justify-end pt-2">
              <button type="button" onClick={() => setEditUser(null)} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800">
                Close
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
