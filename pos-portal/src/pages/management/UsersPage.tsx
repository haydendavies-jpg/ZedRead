/** POS user access grants management page — list, grant, revoke, and bulk-update grants in scope. */

import { useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useAuth, isMgmtUser, isSuperAdmin } from '../../context/AuthContext'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { EntityIdChip } from '../../components/EntityIdChip'
import { ScopeGuard } from '../../components/ScopeGuard'
import { Modal } from '../../components/Modal'
import { FilterBar, type FilterConfig } from '../../components/FilterBar'
import { apiErrorMessage } from '../../utils/apiError'
import type { AccessGrant, AccessGrantBulkResult } from '../../types'

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
  const { data } = await api.get('/access-profiles', { params: { brand_id: brandId, limit: 200 } })
  return data
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
  // SuperAdmins reach this page via the Brand detail "Users & Grants" tab. The
  // backend gives them full grant authority (access_grant_service bypasses the
  // scope and role-ceiling checks for portal admins), so the ceiling/scope
  // machinery below — which is derived from a management user's own grant —
  // does not apply to them.
  const superadmin = isSuperAdmin(user)

  const params = brandId ? { brand_id: brandId } : {}

  const { data: grants = [], isLoading } = useQuery<AccessGrant[]>({
    queryKey: ['access-grants', brandId],
    queryFn: () => api.get('/access-grants', { params }).then((r) => r.data),
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
    if (!confirm(`Revoke ${selectedIds.length} grant(s)?`)) return
    setBulkResult(null); setBulkError(null)
    bulkRevoke.mutate(selectedIds)
  }

  // ── Grant-creation form state ────────────────────────────────────────────
  const [showGrant, setShowGrant] = useState(false)
  const [grantUserId, setGrantUserId] = useState('')
  const [grantScope, setGrantScope] = useState<'brand' | 'site'>(scopeOptions[0])
  const [grantEntityId, setGrantEntityId] = useState('')
  const [grantProfileId, setGrantProfileId] = useState('')
  const [grantError, setGrantError] = useState<string | null>(null)

  const openGrant = () => {
    setGrantUserId(''); setGrantEntityId(''); setGrantProfileId('')
    setGrantScope(scopeOptions[0])
    setGrantError(null)
    setShowGrant(true)
  }

  const createGrant = useMutation({
    mutationFn: (body: { user_id: string; scope: string; site_id?: string; brand_id?: string; access_profile_id: string }) =>
      api.post('/access-grants', body),
    onSuccess: () => {
      invalidateGrants()
      setShowGrant(false)
    },
    onError: (e: unknown) => {
      invalidateGrants()
      setGrantError(apiErrorMessage(e, 'Failed to grant access.'))
    },
  })

  const handleGrantSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setGrantError(null)
    const body: { user_id: string; scope: string; site_id?: string; brand_id?: string; access_profile_id: string } = {
      user_id: grantUserId,
      scope: grantScope,
      access_profile_id: grantProfileId,
    }
    if (grantScope === 'site') body.site_id = grantEntityId
    else body.brand_id = grantEntityId
    createGrant.mutate(body)
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
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Users &amp; Grants</h1>
        <button
          onClick={openGrant}
          disabled={!canGrant}
          title={!canGrant ? 'Your own access profile could not be determined' : undefined}
          className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + Grant Access
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
                Updated {bulkResult.succeeded.length} grant(s).
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
                      <td className="px-4 py-3 text-right">
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
                      {grants.length === 0 ? 'No active grants in scope.' : 'No grants match the current filters.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {showGrant && (
        <Modal title="Grant Access" onClose={() => setShowGrant(false)}>
          <form onSubmit={handleGrantSubmit} className="flex flex-col gap-3">
            <p className="text-xs text-gray-400 dark:text-gray-500">
              You can only grant scope and access at or below your own level — the server
              re-checks this regardless of what's shown here.
            </p>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400">User ID</label>
              <input
                type="text"
                required
                value={grantUserId}
                onChange={(e) => setGrantUserId(e.target.value)}
                placeholder="Existing user's UUID"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>

            {scopeOptions.length > 1 && (
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Scope</label>
                <select
                  value={grantScope}
                  onChange={(e) => setGrantScope(e.target.value as 'brand' | 'site')}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
                >
                  {scopeOptions.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
            )}

            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
                {grantScope === 'site' ? 'Site ID' : 'Brand ID'}
              </label>
              <input
                type="text"
                required
                value={grantEntityId}
                onChange={(e) => setGrantEntityId(e.target.value)}
                placeholder={grantScope === 'site' ? "Site's UUID" : "Brand's UUID"}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>

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

            {grantError && <p className="text-xs text-red-500">{grantError}</p>}

            <button
              type="submit"
              disabled={createGrant.isPending}
              className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors mt-1"
            >
              Grant Access
            </button>
          </form>
        </Modal>
      )}
    </div>
  )
}
