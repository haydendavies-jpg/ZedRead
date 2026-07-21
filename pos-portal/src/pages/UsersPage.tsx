/**
 * Admin portal page for managing Users — list, create, edit (grants, PIN, backend role,
 * admin-portal role). Condenses what used to be two separate pages (SuperAdmins + Users):
 * admin-portal access is now just a superadmin_role on the same User row, not a distinct
 * identity type, so one page/table covers both tenant staff and portal admins.
 */

import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, fetchAll } from '../api/axios'
import type { Brand, Site, User } from '../types'
import { EntityIdChip } from '../components/EntityIdChip'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'
import { FilterBar, type FilterConfig } from '../components/FilterBar'
import { apiErrorMessage } from '../utils/apiError'
import { isSuperAdmin, useAuth } from '../context/AuthContext'

// ── Types ─────────────────────────────────────────────────────────────────────

interface AccessProfile {
  id: string
  name: string
  can_access_portal: boolean
}

/** Result of GET /users/email-check — whether the typed email already exists. */
interface EmailCheckResult {
  exists: boolean
  display_name?: string
  has_password?: boolean
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
  return fetchAll<Brand>('/brands/')
}

async function fetchSites(): Promise<Site[]> {
  return fetchAll<Site>('/sites/')
}

async function fetchUsers(brandId: string): Promise<User[]> {
  const params: Record<string, unknown> = {}
  if (brandId) params.brand_id = brandId
  return fetchAll<User>('/users', params)
}

async function fetchProfiles(brandId: string | null): Promise<AccessProfile[]> {
  if (!brandId) return []
  return fetchAll<AccessProfile>('/access-profiles', { brand_id: brandId })
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

const SUPERADMIN_ROLES = [
  { value: 'admin', label: 'Admin' },
  { value: 'reseller_staff', label: 'Reseller' },
]

// ── Component ─────────────────────────────────────────────────────────────────

export function UsersPage() {
  const qc = useQueryClient()
  const { user: currentUser } = useAuth()
  // Any portal admin may set another user's password; only an Admin-role portal
  // admin may grant/change the admin-portal role itself (mirrors the backend's
  // require_super_admin gate on superadmin_role changes in routes/users.py).
  const canSetPassword = isSuperAdmin(currentUser)
  const canManageSuperadminRole = isSuperAdmin(currentUser) && currentUser.superadmin_role === 'admin'

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
  const [portalAccessFilter, setPortalAccessFilter] = useState('')
  const [superadminRoleFilter, setSuperadminRoleFilter] = useState('')

  // ── Create user state ─────────────────────────────────────────────────────
  const [showCreate, setShowCreate] = useState(false)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [createSuperadminRole, setCreateSuperadminRole] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)

  // Detect an already-registered email while the admin types, so the form can
  // skip the password step: a shared email links the new user to the existing
  // identity's sign-in password, and they pick the platform at login.
  const [debouncedEmail, setDebouncedEmail] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setDebouncedEmail(email), 350)
    return () => clearTimeout(t)
  }, [email])
  const emailLooksValid = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(debouncedEmail)
  const { data: emailCheck } = useQuery<EmailCheckResult>({
    queryKey: ['email-check', debouncedEmail],
    queryFn: () => api.get('/users/email-check', { params: { email: debouncedEmail } }).then((r) => r.data),
    enabled: showCreate && emailLooksValid,
    staleTime: 30_000,
  })
  // "Linked" = reuse the existing password (only possible when that account
  // actually has one); otherwise the password field stays required.
  const linkedEmail = !!(emailCheck?.exists && emailCheck.has_password)

  // ── Edit user state ───────────────────────────────────────────────────────
  const [editUser, setEditUser] = useState<User | null>(null)
  const [editFirstName, setEditFirstName] = useState('')
  const [editLastName, setEditLastName] = useState('')
  const [editEmail, setEditEmail] = useState('')
  const [editPassword, setEditPassword] = useState('')
  const [editSuperadminRole, setEditSuperadminRole] = useState('')
  const [editPosMultiSiteEnabled, setEditPosMultiSiteEnabled] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)
  const [resetSent, setResetSent] = useState(false)

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
    // A pure admin-portal row (no group_id) has nothing to show here.
    enabled: !!editUser && !!editUser.brand_id,
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
    mutationFn: (body: { brand_id: string | null; first_name: string; last_name: string; email: string; password?: string; superadmin_role: string | null }) =>
      api.post('/users', body),
    onSuccess: () => {
      invalidateUsers()
      setShowCreate(false)
      setFirstName(''); setLastName(''); setEmail(''); setPassword(''); setCreateSuperadminRole('')
      setCreateError(null)
    },
    onError: (e: unknown) => {
      invalidateUsers()
      setCreateError(apiErrorMessage(e, 'Failed to create user.'))
    },
  })

  const editMutation = useMutation({
    mutationFn: ({ id, firstName, lastName, email, superadminRole, password, isPosMultiSiteEnabled }: { id: string; firstName: string; lastName: string; email: string; superadminRole?: string | null; password?: string; isPosMultiSiteEnabled: boolean }) =>
      api.patch(`/users/${id}`, {
        first_name: firstName,
        last_name: lastName,
        email,
        is_pos_multi_site_enabled: isPosMultiSiteEnabled,
        ...(superadminRole !== undefined ? { superadmin_role: superadminRole } : {}),
        ...(password ? { password } : {}),
      }),
    onSuccess: () => {
      invalidateUsers()
      setEditError(null)
      setEditPassword('')
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
    mutationFn: (body: { user_id: string; scope: string; site_id?: string; brand_id?: string; access_profile_id: string; backend_role?: string | null }) =>
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
    onError: (e: unknown) => { invalidateUsers(); alert(apiErrorMessage(e, 'Failed to deactivate user.')) },
  })

  const reactivateMutation = useMutation({
    mutationFn: (userId: string) => api.post(`/users/${userId}/reactivate`),
    onSuccess: invalidateUsers,
    onError: (e: unknown) => { invalidateUsers(); alert(apiErrorMessage(e, 'Failed to reactivate user.')) },
  })

  const sendResetMutation = useMutation({
    mutationFn: (userId: string) => api.post(`/users/${userId}/send-password-reset`),
    onSuccess: () => {
      setResetSent(true)
      setTimeout(() => setResetSent(false), 4000)
    },
    onError: (e: unknown) => alert(apiErrorMessage(e, 'Failed to send reset email.')),
  })

  // ── Handlers ──────────────────────────────────────────────────────────────
  const openCreate = () => {
    setFirstName(''); setLastName(''); setEmail(''); setPassword(''); setCreateSuperadminRole(''); setCreateError(null)
    setShowCreate(true)
  }

  const openEdit = (user: User) => {
    // Older rows created before the Stage 15 first/last split carry only a
    // composed `name` — fall back to splitting it on the first space.
    setEditFirstName(user.first_name ?? user.name.split(' ')[0] ?? '')
    setEditLastName(user.last_name ?? user.name.split(' ').slice(1).join(' '))
    setEditEmail(user.email ?? '')
    setEditPassword('')
    setEditSuperadminRole(user.superadmin_role ?? '')
    setEditPosMultiSiteEnabled(user.is_pos_multi_site_enabled)
    setEditError(null)
    setPinValue(''); setPinError(null); setPinSuccess(false)
    setAccessSearch('')
    setResetSent(false)
    setEditUser(user)
  }

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    setCreateError(null)
    // Omit the password for a linked email — the backend reuses the existing
    // identity's sign-in password and rejects a competing one.
    const body = {
      brand_id: selectedBrandId || null,
      first_name: firstName,
      last_name: lastName,
      email,
      superadmin_role: createSuperadminRole || null,
    }
    createMutation.mutate(linkedEmail ? body : { ...body, password })
  }

  const handleEditSave = (e: React.FormEvent) => {
    e.preventDefault()
    if (!editUser) return
    setEditError(null)
    if (canSetPassword && editPassword && editPassword.length < 8) {
      setEditError('Password must be at least 8 characters.')
      return
    }
    editMutation.mutate({
      id: editUser.id,
      firstName: editFirstName,
      lastName: editLastName,
      email: editEmail,
      isPosMultiSiteEnabled: editPosMultiSiteEnabled,
      ...(canManageSuperadminRole ? { superadminRole: editSuperadminRole || null } : {}),
      ...(canSetPassword && editPassword ? { password: editPassword } : {}),
    })
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

  /**
   * Called when the Backend Access dropdown changes for any row.
   *
   * Backend access no longer requires POS access to already be assigned —
   * if the row has no grant yet, one is created in the same request using
   * the row's currently-selected POS profile, or "Reporting Only" (the
   * system profile ROLE_MODEL.md documents as backend-oriented, POS-access
   * N/A) as a sensible default when none is selected.
   */
  const handleBackendRoleChange = (entry: GroupScopeEntry, newRole: string) => {
    if (!editUser) return
    if (entry.grant_id) {
      updateGrantBackendRoleMutation.mutate({ grantId: entry.grant_id, backendRole: newRole || null })
      return
    }
    if (!newRole) return // nothing to create just to set "No access"
    // Group-scope grants only ever exist via the site/brand cascade in
    // create_grant() — there's no group_id on this row to create one directly.
    if (entry.scope === 'group') {
      alert('Assign backend access at the brand or site level first.')
      return
    }
    const defaultProfileId =
      entry.access_profile_id ??
      editUserProfiles.find((p) => p.name === 'Reporting Only')?.id ??
      editUserProfiles[0]?.id
    if (!defaultProfileId) {
      alert('No access profiles are available for this brand yet.')
      return
    }
    const body: { user_id: string; scope: string; site_id?: string; brand_id?: string; access_profile_id: string; backend_role?: string | null } = {
      user_id: editUser.id, scope: entry.scope, access_profile_id: defaultProfileId, backend_role: newRole,
    }
    if (entry.scope === 'site') body.site_id = entry.site_id ?? undefined
    else body.brand_id = entry.brand_id ?? undefined
    addGrantMutation.mutate(body)
  }

  // ── Filtered data ─────────────────────────────────────────────────────────
  const filtered = users.filter((u) => {
    if (search) {
      const q = search.toLowerCase()
      if (!u.name.toLowerCase().includes(q) && !(u.email ?? '').toLowerCase().includes(q)) return false
    }
    if (statusFilter === 'active' && !u.is_active) return false
    if (statusFilter === 'inactive' && u.is_active) return false
    if (siteFilter && !u.site_grants.some((g) => g.site_name === siteFilter)) return false
    if (portalAccessFilter === 'yes' && !u.has_portal_access) return false
    if (portalAccessFilter === 'no' && u.has_portal_access) return false
    if (superadminRoleFilter === 'none' && u.superadmin_role) return false
    if (superadminRoleFilter && superadminRoleFilter !== 'none' && u.superadmin_role !== superadminRoleFilter) return false
    return true
  })

  const hasFilters = !!(search || statusFilter || siteFilter || portalAccessFilter || superadminRoleFilter)
  const clearFilters = () => {
    setSearch(''); setStatusFilter(''); setSiteFilter(''); setPortalAccessFilter(''); setSuperadminRoleFilter('')
  }

  const filterConfigs: FilterConfig[] = [
    {
      label: 'Status',
      value: statusFilter,
      onChange: setStatusFilter,
      options: [
        { value: '', label: 'Any' },
        { value: 'active', label: 'Active' },
        { value: 'inactive', label: 'Inactive' },
      ],
    },
    {
      label: 'Site',
      value: siteFilter,
      onChange: setSiteFilter,
      options: [{ value: '', label: 'Any' }, ...brandSites.map((s) => ({ value: s.name, label: s.name }))],
    },
    {
      label: 'Backend Access',
      value: portalAccessFilter,
      onChange: setPortalAccessFilter,
      options: [
        { value: '', label: 'Any' },
        { value: 'yes', label: 'Has access' },
        { value: 'no', label: 'No access' },
      ],
    },
    {
      label: 'Portal Role',
      value: superadminRoleFilter,
      onChange: setSuperadminRoleFilter,
      options: [
        { value: '', label: 'Any' },
        { value: 'none', label: '— none —' },
        ...SUPERADMIN_ROLES,
      ],
    },
  ]

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
          className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New User
        </button>
      </div>

      {/* ── Brand context selector (drives which tenant users load) ───────── */}
      <div className="flex flex-wrap items-end gap-3 mb-1">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Brand</label>
          <select
            value={selectedBrandId}
            onChange={(e) => { setSelectedBrandId(e.target.value); clearFilters() }}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="">Any (incl. admin-portal-only rows)</option>
            {brands.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
        </div>
      </div>

      <FilterBar
        search={search}
        onSearchChange={setSearch}
        searchPlaceholder="Name or email…"
        filters={filterConfigs}
        hasFilters={hasFilters}
        onClear={clearFilters}
        resultCount={filtered.length}
        totalCount={users.length}
      />

      {/* ── Users table ──────────────────────────────────────────────────────── */}
      {isLoading ? (
        <div className="text-gray-400 dark:text-gray-500 text-sm">Loading…</div>
      ) : (
        <div className="zr-table-wrap">
          <table className="zr-table min-w-[980px]">
            <thead>
              <tr>
                <th>ID</th>
                <th>Group</th>
                <th>Brand</th>
                <th>Name</th>
                <th>Email</th>
                <th>Sites</th>
                <th>Management Portal</th>
                <th>Admin Portal</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => (
                <tr key={u.id}>
                  <td><EntityIdChip id={u.id} ref={u.ref} /></td>
                  <td className="text-[var(--zr-muted)]">{u.group_name || <span className="text-[var(--zr-faint)]">—</span>}</td>
                  <td className="text-[var(--zr-muted)]">{u.brand_name || <span className="text-[var(--zr-faint)]">—</span>}</td>
                  <td className="font-medium">
                    {u.name}
                    {u.id === currentUser?.id && <span className="ml-1 text-xs text-brand-400">(you)</span>}
                  </td>
                  <td className="text-[var(--zr-muted)]">{u.email ?? <span className="text-[var(--zr-faint)]">—</span>}</td>
                  <td className="zr-cell-pad">
                    {u.site_grants.length === 0 ? (
                      <span className="text-xs text-[var(--zr-faint)]">None</span>
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
                  <td>
                    {u.has_portal_access ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300">
                        Yes
                      </span>
                    ) : (
                      <span className="text-xs text-[var(--zr-faint)]">—</span>
                    )}
                  </td>
                  <td>
                    {u.superadmin_role ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-brand-50 dark:bg-brand-950/30 text-brand-700 dark:text-brand-400">
                        {SUPERADMIN_ROLES.find((r) => r.value === u.superadmin_role)?.label ?? u.superadmin_role}
                      </span>
                    ) : (
                      <span className="text-xs text-[var(--zr-faint)]">—</span>
                    )}
                  </td>
                  <td>
                    <StatusBadge status={u.is_active ? 'active' : 'disabled'} />
                  </td>
                  <td className="zr-cell-pad">
                    <div className="flex flex-wrap items-center gap-3">
                      <button onClick={() => openEdit(u)} className="text-brand-600 hover:underline text-xs">Edit</button>
                      {u.id !== currentUser?.id && (
                        u.is_active ? (
                          <button onClick={() => deactivateMutation.mutate(u.id)} className="text-red-500 hover:underline text-xs">
                            Deactivate
                          </button>
                        ) : (
                          <button onClick={() => reactivateMutation.mutate(u.id)} className="text-green-600 hover:underline text-xs">
                            Reactivate
                          </button>
                        )
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={10} className="text-center text-[var(--zr-faint)] py-8">
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
            {linkedEmail ? (
              <div className="rounded-lg border border-brand-200 bg-brand-50 dark:bg-brand-950/30 dark:border-brand-900 px-3 py-2.5">
                <p className="text-sm text-brand-800 dark:text-brand-300">
                  This email already has an account{emailCheck?.display_name ? ` (${emailCheck.display_name})` : ''}.
                </p>
                <p className="text-xs text-brand-700 dark:text-brand-400 mt-1">
                  No new password needed — the user signs in with the existing password and chooses which account to open at login.
                </p>
              </div>
            ) : (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Password</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={createSuperadminRole ? 6 : 8}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder={createSuperadminRole ? 'Min 6 characters' : 'Min 8 characters'} />
              </div>
            )}
            {canManageSuperadminRole && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Portal Role</label>
                <select
                  value={createSuperadminRole}
                  onChange={(e) => setCreateSuperadminRole(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                >
                  <option value="">— none (ordinary tenant user) —</option>
                  {SUPERADMIN_ROLES.map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                  Grants admin-portal access. Only visible/grantable to Admin-role portal admins.
                  {!selectedBrandId && ' Leave the Brand filter above unset to create a pure admin-portal row with no tenant scope.'}
                </p>
              </div>
            )}
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
                {canManageSuperadminRole && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Portal Role</label>
                    <select
                      value={editSuperadminRole}
                      onChange={(e) => setEditSuperadminRole(e.target.value)}
                      disabled={editUser.id === currentUser?.id}
                      className="w-full sm:w-1/3 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                    >
                      <option value="">— none (ordinary tenant user) —</option>
                      {SUPERADMIN_ROLES.map((r) => (
                        <option key={r.value} value={r.value}>{r.label}</option>
                      ))}
                    </select>
                    {editUser.id === currentUser?.id && (
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">You cannot change your own admin-portal role.</p>
                    )}
                  </div>
                )}
                <div>
                  <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editPosMultiSiteEnabled}
                      onChange={(e) => setEditPosMultiSiteEnabled(e.target.checked)}
                      className="rounded"
                    />
                    POS - Site Assignment
                  </label>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    When enabled and this user holds access to more than one site, POS login prompts them to choose a site instead of using the terminal's paired site automatically.
                  </p>
                </div>
                {canSetPassword && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Set password</label>
                    <input type="password" autoComplete="new-password" value={editPassword}
                      onChange={(e) => setEditPassword(e.target.value)}
                      placeholder="Leave blank to keep the current password"
                      className="w-full sm:w-1/3 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                      At least 8 characters.
                    </p>
                  </div>
                )}
                {editError && <p className="text-sm text-red-600">{editError}</p>}
                <div className="flex items-center justify-between gap-3">
                  <div>
                    {editUser.email ? (
                      <button
                        type="button"
                        onClick={() => sendResetMutation.mutate(editUser.id)}
                        disabled={sendResetMutation.isPending}
                        className="text-brand-600 hover:underline text-xs font-medium disabled:opacity-50"
                      >
                        {sendResetMutation.isPending ? 'Sending…' : resetSent ? 'Reset email sent' : 'Send password reset email'}
                      </button>
                    ) : (
                      <span className="text-xs text-gray-400 dark:text-gray-500">Add an email to enable password reset</span>
                    )}
                  </div>
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

              {!editUser.brand_id ? (
                <p className="text-xs text-[var(--zr-faint)] py-4 text-center">
                  This is a pure admin-portal row with no tenant scope — there is no site/brand access to manage.
                </p>
              ) : (
              <div className="zr-table-wrap">
                <table className="zr-table min-w-[680px]">
                  <thead>
                    <tr>
                      <th>Brand</th>
                      <th>Site</th>
                      <th>POS Access</th>
                      <th>Backend Access</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {accessLoading ? (
                      <tr><td colSpan={5} className="text-center text-[var(--zr-faint)] text-xs py-4">Loading…</td></tr>
                    ) : filteredEntries.length === 0 ? (
                      <tr><td colSpan={5} className="text-center text-[var(--zr-faint)] text-xs py-4">
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
              )}
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
