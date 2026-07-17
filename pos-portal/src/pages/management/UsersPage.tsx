/** Users & Access management page — list, edit, add, revoke, and bulk-update access in scope. */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, fetchAll } from '../../api/axios'
import { useAuth, isMgmtUser, isSuperAdmin } from '../../context/AuthContext'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { EntityIdChip } from '../../components/EntityIdChip'
import { ScopeGuard } from '../../components/ScopeGuard'
import { Modal } from '../../components/Modal'
import { FilterBar, type FilterConfig } from '../../components/FilterBar'
import { apiErrorMessage } from '../../utils/apiError'
import type { AccessGrant, AccessGrantBulkResult, SiteOption, UserSearchResult } from '../../types'

// Mirrors app.services.access_grant_service._ROLE_RANK — used only to filter
// which profiles this UI offers to grant. The backend enforces the real
// ceiling (Stage 17); this is client-side UX only, never the source of truth.
const ROLE_RANK: Record<string, number> = {
  Staff: 1,
  'Reporting Only': 2,
  Manager: 3,
  Admin: 4,
  'Master User': 5,
}
const UNRANKED_PROFILE_RANK = ROLE_RANK.Admin

function roleRank(name: string): number {
  return ROLE_RANK[name] ?? UNRANKED_PROFILE_RANK
}

// Backend-access roles a grant may carry — mirrors routes/users.py _BACKEND_ROLES.
const BACKEND_ROLES = [
  { value: 'admin', label: 'Admin' },
  { value: 'users', label: 'Users' },
  { value: 'reporting', label: 'Reporting' },
]

interface AccessProfileOption {
  id: string
  name: string
  is_system: boolean
}

async function fetchProfiles(brandId: string): Promise<AccessProfileOption[]> {
  return fetchAll<AccessProfileOption>('/access-profiles', { brand_id: brandId })
}

export function UsersPage() {
  return (
    <ScopeGuard minScope="brand">
      <UsersPageInner />
    </ScopeGuard>
  )
}

function UsersPageInner() {
  const qc = useQueryClient()
  const brandId = useMgmtBrandId()
  const { user } = useAuth()
  const mgmtUser = isMgmtUser(user) ? user : null
  // SuperAdmins reach this page via the Brand detail "Users & Access" tab. The
  // backend gives them full grant authority (access_grant_service bypasses the
  // scope and role-ceiling checks for portal admins), so the ceiling/scope
  // machinery below — which is derived from a management user's own grant —
  // does not apply to them.
  const superadmin = isSuperAdmin(user)

  const params = brandId ? { brand_id: brandId } : {}

  const { data: grants = [], isLoading } = useQuery<AccessGrant[]>({
    queryKey: ['access-grants', brandId],
    queryFn: () => fetchAll<AccessGrant>('/access-grants', params),
    enabled: brandId !== undefined,
  })

  const { data: profiles = [] } = useQuery<AccessProfileOption[]>({
    queryKey: ['access-profiles', brandId],
    queryFn: () => fetchProfiles(brandId!),
    enabled: !!brandId,
  })

  const profileName = (id: string): string => profiles.find((p) => p.id === id)?.name ?? ''

  // The caller's own profile — used to cap which profiles a management user may
  // grant. Their own grant is always among the fetched grants (it's within their
  // scope). SuperAdmins have no such grant here, so the ceiling does not apply.
  const ownProfileId = grants.find((g) => g.id === mgmtUser?.grant_id)?.access_profile_id
  const ownRank = ownProfileId ? roleRank(profileName(ownProfileId)) : 0
  // SuperAdmins may grant any profile except Master User (which the backend
  // never delegates); management users are capped at their own rank.
  const grantableProfiles = superadmin
    ? profiles.filter((p) => p.name !== 'Master User')
    : profiles.filter((p) => roleRank(p.name) <= ownRank)

  // Whether the caller may create grants at all. SuperAdmins always may; a
  // management user needs their own profile resolved first (to enforce the ceiling).
  const canGrant = superadmin || !!ownProfileId

  // SuperAdmins and group-scope callers may grant brand or site scope; brand-scope
  // callers may only grant site scope (matches access_grant_service._assert_create_authority).
  const scopeOptions = useMemo<Array<'brand' | 'site'>>(() => {
    if (superadmin || mgmtUser?.scope === 'group') return ['brand', 'site']
    return ['site']
  }, [superadmin, mgmtUser?.scope])

  // ── Filters ────────────────────────────────────────────────────────────────
  const [search, setSearch] = useState('')
  const [scopeFilter, setScopeFilter] = useState('')
  const [profileFilter, setProfileFilter] = useState('')
  const [backendFilter, setBackendFilter] = useState('')

  const filtered = grants.filter((g) => {
    if (search) {
      const q = search.toLowerCase()
      const hay = `${g.user_name ?? ''} ${g.user_email ?? ''} ${g.user_ref ?? ''}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    if (scopeFilter && g.scope !== scopeFilter) return false
    if (profileFilter && g.access_profile_id !== profileFilter) return false
    if (backendFilter === 'none' && g.backend_role) return false
    if (backendFilter && backendFilter !== 'none' && g.backend_role !== backendFilter) return false
    return true
  })

  const hasFilters = !!(search || scopeFilter || profileFilter || backendFilter)
  const clearFilters = () => { setSearch(''); setScopeFilter(''); setProfileFilter(''); setBackendFilter('') }

  const filters: FilterConfig[] = [
    {
      label: 'Scope',
      value: scopeFilter,
      onChange: setScopeFilter,
      options: [
        { value: '', label: 'All scopes' },
        { value: 'site', label: 'Site' },
        { value: 'brand', label: 'Brand' },
        { value: 'group', label: 'Group' },
      ],
    },
    {
      label: 'Profile',
      value: profileFilter,
      onChange: setProfileFilter,
      options: [{ value: '', label: 'All profiles' }, ...profiles.map((p) => ({ value: p.id, label: p.name }))],
    },
    {
      label: 'Backend access',
      value: backendFilter,
      onChange: setBackendFilter,
      options: [
        { value: '', label: 'Any' },
        { value: 'none', label: 'None' },
        ...BACKEND_ROLES.map((r) => ({ value: r.value, label: r.label })),
      ],
    },
  ]

  // ── Selection ────────────────────────────────────────────────────────────────
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const filteredIds = filtered.map((g) => g.id)
  const allSelected = filteredIds.length > 0 && filteredIds.every((id) => selected.has(id))
  const someSelected = filteredIds.some((id) => selected.has(id))
  const selectAllRef = useRef<HTMLInputElement>(null)
  if (selectAllRef.current) selectAllRef.current.indeterminate = someSelected && !allSelected

  const toggleOne = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  const toggleAll = () => {
    setSelected((prev) => {
      if (filteredIds.every((id) => prev.has(id))) {
        // Deselect the currently-visible rows only
        const next = new Set(prev)
        filteredIds.forEach((id) => next.delete(id))
        return next
      }
      return new Set([...prev, ...filteredIds])
    })
  }
  const clearSelection = () => setSelected(new Set())

  const invalidateGrants = () => qc.invalidateQueries({ queryKey: ['access-grants', brandId] })

  const revoke = useMutation({
    mutationFn: (id: string) => api.delete(`/access-grants/${id}`),
    onSuccess: invalidateGrants,
    onError: (e: unknown) => {
      invalidateGrants()
      alert(apiErrorMessage(e, 'Failed to revoke access.'))
    },
  })

  const [resetSent, setResetSent] = useState(false)
  const sendReset = useMutation({
    mutationFn: (userId: string) => api.post(`/users/${userId}/send-password-reset`),
    onSuccess: () => {
      setResetSent(true)
      setTimeout(() => setResetSent(false), 4000)
    },
    onError: (e: unknown) => alert(apiErrorMessage(e, 'Failed to send reset email.')),
  })

  // ── Bulk actions ─────────────────────────────────────────────────────────────
  const [bulkResult, setBulkResult] = useState<AccessGrantBulkResult | null>(null)
  const [bulkError, setBulkError] = useState<string | null>(null)

  const onBulkSuccess = (data: AccessGrantBulkResult) => {
    invalidateGrants()
    setBulkResult(data)
    setBulkError(null)
    // Keep only the failed grants selected so the user can retry/inspect them.
    setSelected(new Set(data.errors.map((e) => e.grant_id)))
  }
  const onBulkError = (e: unknown) => {
    invalidateGrants()
    setBulkResult(null)
    setBulkError(apiErrorMessage(e, 'Bulk action failed.'))
  }

  const bulkUpdate = useMutation({
    mutationFn: (body: { grant_ids: string[]; access_profile_id?: string; backend_role?: string | null }) =>
      api.post('/access-grants/bulk-update', body).then((r) => r.data as AccessGrantBulkResult),
    onSuccess: onBulkSuccess,
    onError: onBulkError,
  })
  const bulkRevoke = useMutation({
    mutationFn: (grant_ids: string[]) =>
      api.post('/access-grants/bulk-revoke', { grant_ids }).then((r) => r.data as AccessGrantBulkResult),
    onSuccess: onBulkSuccess,
    onError: onBulkError,
  })

  const selectedIds = [...selected]
  const bulkPending = bulkUpdate.isPending || bulkRevoke.isPending

  const applyBulkProfile = (profileId: string) => {
    if (!profileId) return
    setBulkResult(null); setBulkError(null)
    bulkUpdate.mutate({ grant_ids: selectedIds, access_profile_id: profileId })
  }
  const applyBulkBackend = (value: string) => {
    if (!value) return
    setBulkResult(null); setBulkError(null)
    // 'none' clears the backend role (explicit null); otherwise set the role.
    bulkUpdate.mutate({ grant_ids: selectedIds, backend_role: value === 'none' ? null : value })
  }
  const applyBulkRevoke = () => {
    if (selectedIds.length === 0) return
    if (!confirm(`Revoke ${selectedIds.length} access record(s)?`)) return
    setBulkResult(null); setBulkError(null)
    bulkRevoke.mutate(selectedIds)
  }

  // ── Add-user / add-access form state ─────────────────────────────────────
  // "existing" grants additional access to a user found by search (the
  // original flow); "new" onboards a brand-new colleague in the same step —
  // until this was added there was no way to create a user from the
  // management portal at all, only a SuperAdmin's separate /users route.
  const [showGrant, setShowGrant] = useState(false)
  const [addMode, setAddMode] = useState<'existing' | 'new'>('existing')
  const [grantUserId, setGrantUserId] = useState('')
  const [grantUserQuery, setGrantUserQuery] = useState('')
  const [grantUserOpen, setGrantUserOpen] = useState(false)
  const [newFirstName, setNewFirstName] = useState('')
  const [newLastName, setNewLastName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [grantScope, setGrantScope] = useState<'brand' | 'site'>(scopeOptions[0])
  // Multiple sites may be selected at once — one grant per site, same user/profile/backend role.
  const [grantSites, setGrantSites] = useState<SiteOption[]>([])
  const [siteQuery, setSiteQuery] = useState('')
  const [siteOpen, setSiteOpen] = useState(false)
  const [grantProfileId, setGrantProfileId] = useState('')
  const [grantBackendRole, setGrantBackendRole] = useState('')
  const [grantError, setGrantError] = useState<string | null>(null)
  const [grantSubmitting, setGrantSubmitting] = useState(false)

  const openGrant = () => {
    setAddMode('existing')
    setGrantUserId(''); setGrantUserQuery(''); setGrantUserOpen(false)
    setNewFirstName(''); setNewLastName(''); setNewEmail(''); setNewPassword('')
    setGrantSites([]); setSiteQuery(''); setSiteOpen(false)
    setGrantProfileId(''); setGrantBackendRole('')
    setGrantScope(scopeOptions[0])
    setGrantError(null)
    setShowGrant(true)
  }

  // Debounce the search boxes so we don't fire a request on every keystroke.
  const [debouncedGrantUserQuery, setDebouncedGrantUserQuery] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setDebouncedGrantUserQuery(grantUserQuery.trim()), 300)
    return () => clearTimeout(t)
  }, [grantUserQuery])

  const { data: userResults = [], isFetching: userSearchLoading } = useQuery<UserSearchResult[]>({
    queryKey: ['user-search', brandId, debouncedGrantUserQuery],
    queryFn: () =>
      api
        .get<UserSearchResult[]>('/access-grants/user-search', {
          params: { brand_id: brandId, q: debouncedGrantUserQuery, limit: 10 },
        })
        .then((r) => r.data),
    enabled: showGrant && addMode === 'existing' && !!brandId && debouncedGrantUserQuery.length > 0 && !grantUserId,
  })

  const selectGrantUser = (u: UserSearchResult) => {
    setGrantUserId(u.id)
    setGrantUserQuery(`${u.name} (${u.email})`)
    setGrantUserOpen(false)
  }

  const [debouncedSiteQuery, setDebouncedSiteQuery] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSiteQuery(siteQuery.trim()), 300)
    return () => clearTimeout(t)
  }, [siteQuery])

  const { data: siteResults = [], isFetching: siteSearchLoading } = useQuery<SiteOption[]>({
    queryKey: ['grantable-sites', brandId, debouncedSiteQuery],
    queryFn: () =>
      api
        .get<SiteOption[]>('/access-grants/grantable-sites', {
          params: { brand_id: brandId, q: debouncedSiteQuery, limit: 50 },
        })
        .then((r) => r.data),
    enabled: showGrant && grantScope === 'site' && !!brandId,
  })

  const toggleGrantSite = (site: SiteOption) => {
    setGrantSites((prev) => (prev.some((s) => s.id === site.id) ? prev.filter((s) => s.id !== site.id) : [...prev, site]))
  }

  const handleGrantSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setGrantError(null)

    if (!grantProfileId) {
      setGrantError('Select an access profile.')
      return
    }
    const siteIds = grantScope === 'site' ? grantSites.map((s) => s.id) : []
    if (grantScope === 'site' && siteIds.length === 0) {
      setGrantError('Select at least one site.')
      return
    }
    if (addMode === 'existing' && !grantUserId) {
      setGrantError('Search for the user by name or email and select them from the results.')
      return
    }
    if (addMode === 'new' && (!newFirstName.trim() || !newLastName.trim())) {
      setGrantError('First and last name are required.')
      return
    }

    const firstEntityId = grantScope === 'site' ? siteIds[0] : brandId!
    const backendRole = grantBackendRole || null

    setGrantSubmitting(true)
    try {
      let userId = grantUserId
      if (addMode === 'new') {
        const body: Record<string, unknown> = {
          first_name: newFirstName, last_name: newLastName,
          email: newEmail || undefined, password: newPassword || undefined,
          scope: grantScope, access_profile_id: grantProfileId, backend_role: backendRole,
        }
        if (grantScope === 'site') body.site_id = firstEntityId
        else body.brand_id = firstEntityId
        const { data } = await api.post('/access-grants/create-user', body)
        userId = data.user_id
      } else {
        const body: Record<string, unknown> = {
          user_id: grantUserId, scope: grantScope, access_profile_id: grantProfileId, backend_role: backendRole,
        }
        if (grantScope === 'site') body.site_id = firstEntityId
        else body.brand_id = firstEntityId
        await api.post('/access-grants', body)
      }
      // Any additional selected sites become extra grants for the same user/profile/backend role.
      for (const siteId of siteIds.slice(1)) {
        await api.post('/access-grants', {
          user_id: userId, scope: 'site', site_id: siteId, access_profile_id: grantProfileId, backend_role: backendRole,
        })
      }
      invalidateGrants()
      setShowGrant(false)
    } catch (err) {
      invalidateGrants()
      setGrantError(apiErrorMessage(err, addMode === 'new' ? 'Failed to create user.' : 'Failed to add access.'))
    } finally {
      setGrantSubmitting(false)
    }
  }

  // ── Edit-user modal state ────────────────────────────────────────────────
  // Edits the grant row's profile/backend access; email is only editable here
  // by SuperAdmins, since PATCH /users/{id} is a portal-admin-only route —
  // management users see it read-only instead of a control that would 403.
  const [editGrant, setEditGrant] = useState<AccessGrant | null>(null)
  const [editEmail, setEditEmail] = useState('')
  const [editProfileId, setEditProfileId] = useState('')
  const [editBackend, setEditBackend] = useState('')
  const [editError, setEditError] = useState<string | null>(null)
  const [editSubmitting, setEditSubmitting] = useState(false)

  const openEdit = (g: AccessGrant) => {
    setEditGrant(g)
    setEditEmail(g.user_email ?? '')
    setEditProfileId(g.access_profile_id)
    setEditBackend(g.backend_role ?? '')
    setEditError(null)
    setResetSent(false)
  }

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editGrant) return
    setEditError(null)
    setEditSubmitting(true)
    try {
      if (superadmin && editEmail !== (editGrant.user_email ?? '')) {
        await api.patch(`/users/${editGrant.user_id}`, { email: editEmail })
      }
      await api.patch(`/access-grants/${editGrant.id}`, {
        access_profile_id: editProfileId,
        backend_role: editBackend || null,
      })
      invalidateGrants()
      setEditGrant(null)
    } catch (err) {
      invalidateGrants()
      setEditError(apiErrorMessage(err, 'Failed to update user.'))
    } finally {
      setEditSubmitting(false)
    }
  }

  if (!brandId) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-gray-400 dark:text-gray-500">
        No brand context available.
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Users &amp; Access</h1>
        <button
          onClick={openGrant}
          disabled={!canGrant}
          title={!canGrant ? 'Your own access profile could not be determined' : undefined}
          className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + Add User
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
      ) : (
        <>
          <FilterBar
            search={search}
            onSearchChange={setSearch}
            searchPlaceholder="Search name, username, or code…"
            filters={filters}
            hasFilters={hasFilters}
            onClear={clearFilters}
            resultCount={filtered.length}
            totalCount={grants.length}
          />

          {/* ── Bulk action bar (shown when rows are selected) ──────────────── */}
          {selected.size > 0 && (
            <div className="flex flex-wrap items-center gap-3 mb-3 px-3 py-2 rounded-lg border border-brand-200 dark:border-brand-900 bg-brand-50 dark:bg-brand-950/30">
              <span className="text-sm font-medium text-brand-800 dark:text-brand-300">{selected.size} selected</span>

              <label className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
                Set profile
                <select
                  value=""
                  disabled={bulkPending}
                  onChange={(e) => { applyBulkProfile(e.target.value); e.target.value = '' }}
                  className="px-2 py-1 border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 rounded text-xs focus:outline-none focus:ring-1 focus:ring-brand-500"
                >
                  <option value="">Choose…</option>
                  {grantableProfiles.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </label>

              <label className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
                Set backend
                <select
                  value=""
                  disabled={bulkPending}
                  onChange={(e) => { applyBulkBackend(e.target.value); e.target.value = '' }}
                  className="px-2 py-1 border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 rounded text-xs focus:outline-none focus:ring-1 focus:ring-brand-500"
                >
                  <option value="">Choose…</option>
                  <option value="none">No access</option>
                  {BACKEND_ROLES.map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
              </label>

              <button
                onClick={applyBulkRevoke}
                disabled={bulkPending}
                className="text-xs font-medium text-red-600 hover:text-red-700 disabled:opacity-50"
              >
                Revoke selected
              </button>
              <button
                onClick={clearSelection}
                disabled={bulkPending}
                className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 ml-auto"
              >
                Clear selection
              </button>
            </div>
          )}

          {/* ── Bulk result / error feedback ───────────────────────────────── */}
          {bulkError && <p className="text-xs text-red-500 mb-3">{bulkError}</p>}
          {bulkResult && (
            <div className="text-xs mb-3">
              <p className="text-green-600 dark:text-green-400">
                Updated {bulkResult.succeeded.length} access record(s).
                {bulkResult.errors.length > 0 && ` ${bulkResult.errors.length} skipped:`}
              </p>
              {bulkResult.errors.length > 0 && (
                <ul className="mt-1 list-disc list-inside text-red-500">
                  {bulkResult.errors.map((e) => (
                    <li key={e.grant_id}>{grants.find((g) => g.id === e.grant_id)?.user_name ?? e.grant_id}: {e.detail}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="zr-table-wrap">
            <table className="zr-table min-w-[820px]">
              <thead>
                <tr>
                  <th className="w-10 px-4 py-3">
                    <input
                      ref={selectAllRef}
                      type="checkbox"
                      className="zr-chk"
                      checked={allSelected}
                      onChange={toggleAll}
                      aria-label="Select all"
                    />
                  </th>
                  <th>Name</th>
                  <th>Username</th>
                  <th>User</th>
                  <th>Scope</th>
                  <th>Entity ID</th>
                  <th>Profile</th>
                  <th>Backend</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((g) => {
                  const entityId = g.site_id ?? g.brand_id ?? g.group_id ?? ''
                  return (
                    <tr key={g.id}>
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          className="zr-chk"
                          checked={selected.has(g.id)}
                          onChange={() => toggleOne(g.id)}
                          aria-label={`Select ${g.user_name ?? g.user_id}`}
                        />
                      </td>
                      <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">
                        {g.user_name || <span className="text-gray-300 dark:text-gray-600">—</span>}
                      </td>
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                        {g.user_email || <span className="text-gray-300 dark:text-gray-600">—</span>}
                      </td>
                      <td className="px-4 py-3">
                        <EntityIdChip id={g.user_id} ref={g.user_ref ?? undefined} />
                      </td>
                      <td className="px-4 py-3 text-gray-700 dark:text-gray-300 capitalize">{g.scope}</td>
                      <td className="px-4 py-3">
                        {entityId && <EntityIdChip id={entityId} />}
                      </td>
                      <td className="px-4 py-3 text-gray-700 dark:text-gray-300">
                        {profileName(g.access_profile_id) || <EntityIdChip id={g.access_profile_id} />}
                      </td>
                      <td className="px-4 py-3">
                        {g.backend_role ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 capitalize">
                            {g.backend_role}
                          </span>
                        ) : (
                          <span className="text-xs text-gray-400 dark:text-gray-500">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <button
                          onClick={() => openEdit(g)}
                          className="text-brand-600 hover:underline text-xs font-medium mr-3"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => revoke.mutate(g.id)}
                          disabled={revoke.isPending}
                          className="text-red-500 hover:text-red-700 text-xs font-medium disabled:opacity-50"
                        >
                          Revoke
                        </button>
                      </td>
                    </tr>
                  )
                })}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={9} className="px-4 py-8 text-center text-gray-400 dark:text-gray-500">
                      {grants.length === 0 ? 'No active access in scope.' : 'No access records match the current filters.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {showGrant && (
        <Modal title="Add User" onClose={() => setShowGrant(false)}>
          <form onSubmit={handleGrantSubmit} className="flex flex-col gap-3">
            <p className="text-xs text-gray-400 dark:text-gray-500">
              You can only grant scope and access at or below your own level — the server
              re-checks this regardless of what's shown here.
            </p>

            <div className="flex gap-1 p-0.5 bg-gray-100 dark:bg-gray-800 rounded-lg w-fit">
              <button
                type="button"
                onClick={() => setAddMode('existing')}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${addMode === 'existing' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400'}`}
              >
                Existing user
              </button>
              <button
                type="button"
                onClick={() => setAddMode('new')}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${addMode === 'new' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400'}`}
              >
                New user
              </button>
            </div>

            {addMode === 'existing' ? (
              <div className="flex flex-col gap-1 relative">
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400">User</label>
                <input
                  type="text"
                  required
                  value={grantUserQuery}
                  onChange={(e) => { setGrantUserQuery(e.target.value); setGrantUserId(''); setGrantUserOpen(true) }}
                  onFocus={() => setGrantUserOpen(true)}
                  onBlur={() => setTimeout(() => setGrantUserOpen(false), 150)}
                  placeholder="Search by name or email…"
                  autoComplete="off"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
                {grantUserOpen && !grantUserId && debouncedGrantUserQuery.length > 0 && (
                  <div className="absolute top-full left-0 right-0 mt-1 z-10 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg max-h-56 overflow-y-auto">
                    {userSearchLoading ? (
                      <p className="px-3 py-2 text-xs text-gray-400 dark:text-gray-500">Searching…</p>
                    ) : userResults.length === 0 ? (
                      <p className="px-3 py-2 text-xs text-gray-400 dark:text-gray-500">No matching users.</p>
                    ) : (
                      userResults.map((u) => (
                        <button
                          key={u.id}
                          type="button"
                          onClick={() => selectGrantUser(u)}
                          className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-700"
                        >
                          <span className="font-medium text-gray-900 dark:text-gray-100">{u.name}</span>
                          <span className="text-gray-400 dark:text-gray-500 ml-1.5">{u.email}</span>
                        </button>
                      ))
                    )}
                  </div>
                )}
              </div>
            ) : (
              <>
                <div className="flex gap-3">
                  <div className="flex flex-col gap-1 flex-1">
                    <label className="text-xs font-medium text-gray-500 dark:text-gray-400">First name</label>
                    <input
                      type="text" required value={newFirstName}
                      onChange={(e) => setNewFirstName(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                    />
                  </div>
                  <div className="flex flex-col gap-1 flex-1">
                    <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Last name</label>
                    <input
                      type="text" required value={newLastName}
                      onChange={(e) => setNewLastName(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                    />
                  </div>
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Email (optional unless given backend access)</label>
                  <input
                    type="email" value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Password (optional unless given backend access)</label>
                  <input
                    type="password" value={newPassword} autoComplete="new-password"
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                </div>
              </>
            )}

            {scopeOptions.length > 1 && (
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Scope</label>
                <select
                  value={grantScope}
                  onChange={(e) => { setGrantScope(e.target.value as 'brand' | 'site'); setGrantSites([]) }}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
                >
                  {scopeOptions.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
            )}

            {grantScope === 'site' ? (
              <div className="flex flex-col gap-1 relative">
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Sites</label>
                {grantSites.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-1">
                    {grantSites.map((s) => (
                      <span key={s.id} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-brand-50 dark:bg-brand-950/40 text-brand-700 dark:text-brand-300">
                        {s.name}
                        <button type="button" onClick={() => toggleGrantSite(s)} className="hover:text-brand-900 dark:hover:text-brand-100">×</button>
                      </span>
                    ))}
                  </div>
                )}
                <input
                  type="text"
                  value={siteQuery}
                  onChange={(e) => { setSiteQuery(e.target.value); setSiteOpen(true) }}
                  onFocus={() => setSiteOpen(true)}
                  onBlur={() => setTimeout(() => setSiteOpen(false), 150)}
                  placeholder="Search sites…"
                  autoComplete="off"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
                {siteOpen && (
                  <div className="absolute top-full left-0 right-0 mt-1 z-10 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg max-h-56 overflow-y-auto">
                    {siteSearchLoading ? (
                      <p className="px-3 py-2 text-xs text-gray-400 dark:text-gray-500">Searching…</p>
                    ) : siteResults.length === 0 ? (
                      <p className="px-3 py-2 text-xs text-gray-400 dark:text-gray-500">No matching sites.</p>
                    ) : (
                      siteResults.map((s) => (
                        <button
                          key={s.id}
                          type="button"
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={() => toggleGrantSite(s)}
                          className="w-full flex items-center gap-2 text-left px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-700"
                        >
                          <input type="checkbox" readOnly checked={grantSites.some((g) => g.id === s.id)} className="zr-chk" />
                          <span className="text-gray-900 dark:text-gray-100">{s.name}</span>
                        </button>
                      ))
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Brand</label>
                <div className="px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-900 text-sm text-gray-600 dark:text-gray-400">
                  This brand — access applies brand-wide.
                </div>
              </div>
            )}

            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Access Profile</label>
              <select
                required
                value={grantProfileId}
                onChange={(e) => setGrantProfileId(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="">Select…</option>
                {grantableProfiles.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Backend Access</label>
              <select
                value={grantBackendRole}
                onChange={(e) => setGrantBackendRole(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="">No access</option>
                {BACKEND_ROLES.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>

            {grantError && <p className="text-xs text-red-500">{grantError}</p>}

            <button
              type="submit"
              disabled={grantSubmitting}
              className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors mt-1"
            >
              {addMode === 'new' ? 'Create User' : 'Add Access'}
            </button>
          </form>
        </Modal>
      )}

      {editGrant && (
        <Modal title={`Edit — ${editGrant.user_name ?? editGrant.user_email ?? 'User'}`} onClose={() => setEditGrant(null)}>
          <form onSubmit={handleEditSubmit} className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Email</label>
              {superadmin ? (
                <input
                  type="email"
                  required
                  value={editEmail}
                  onChange={(e) => setEditEmail(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              ) : (
                <p className="text-sm text-gray-500 dark:text-gray-400 px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-900">
                  {editGrant.user_email || '—'}{' '}
                  <span className="text-xs text-gray-400 dark:text-gray-500">(only a SuperAdmin can change email)</span>
                </p>
              )}
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Access Profile</label>
              <select
                required
                value={editProfileId}
                onChange={(e) => setEditProfileId(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                {/* Include the grant's current profile even if it's above what this
                    caller may newly assign, so editing backend access alone doesn't
                    silently downgrade an existing higher-ranked grant. */}
                {!grantableProfiles.some((p) => p.id === editProfileId) && profileName(editProfileId) && (
                  <option value={editProfileId}>{profileName(editProfileId)}</option>
                )}
                {grantableProfiles.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Backend Access</label>
              <select
                value={editBackend}
                onChange={(e) => setEditBackend(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="">No access</option>
                {BACKEND_ROLES.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>

            {editGrant.user_email && (
              <button
                type="button"
                onClick={() => sendReset.mutate(editGrant.user_id)}
                disabled={sendReset.isPending}
                className="text-brand-600 hover:underline text-xs font-medium disabled:opacity-50 text-left"
              >
                {sendReset.isPending ? 'Sending…' : resetSent ? 'Reset email sent' : 'Send password reset email'}
              </button>
            )}

            {editError && <p className="text-xs text-red-500">{editError}</p>}

            <button
              type="submit"
              disabled={editSubmitting}
              className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors mt-1"
            >
              Save Changes
            </button>
          </form>
        </Modal>
      )}
    </div>
  )
}
