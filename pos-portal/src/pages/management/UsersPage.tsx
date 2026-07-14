/** POS user access grants management page — list, grant, and revoke grants in scope. */

import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useAuth, isMgmtUser, isSuperAdmin } from '../../context/AuthContext'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { EntityIdChip } from '../../components/EntityIdChip'
import { ScopeGuard } from '../../components/ScopeGuard'
import { Modal } from '../../components/Modal'
import { apiErrorMessage } from '../../utils/apiError'
import type { AccessGrant } from '../../types'

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

  // The caller's own profile — used to cap which profiles a management user may
  // grant. Their own grant is always among the fetched grants (it's within their
  // scope). SuperAdmins have no such grant here, so the ceiling does not apply.
  const ownProfileId = grants.find((g) => g.id === mgmtUser?.grant_id)?.access_profile_id
  const ownRank = ownProfileId
    ? roleRank(profiles.find((p) => p.id === ownProfileId)?.name ?? '')
    : 0
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

  const revoke = useMutation({
    mutationFn: (id: string) => api.delete(`/access-grants/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['access-grants', brandId] }),
    onError: (e: unknown) => {
      qc.invalidateQueries({ queryKey: ['access-grants', brandId] })
      alert(apiErrorMessage(e, 'Failed to revoke access.'))
    },
  })

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
      qc.invalidateQueries({ queryKey: ['access-grants', brandId] })
      setShowGrant(false)
    },
    onError: (e: unknown) => {
      qc.invalidateQueries({ queryKey: ['access-grants', brandId] })
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
        <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700">
          <table className="w-full text-sm min-w-[500px]">
            <thead className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-400">User ID</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-400">Scope</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-400">Entity ID</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-400">Profile</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {grants.map((g) => {
                const entityId = g.site_id ?? g.brand_id ?? g.group_id ?? ''
                return (
                  <tr key={g.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/60">
                    <td className="px-4 py-3">
                      <EntityIdChip id={g.user_id} />
                    </td>
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300 capitalize">{g.scope}</td>
                    <td className="px-4 py-3">
                      {entityId && <EntityIdChip id={entityId} />}
                    </td>
                    <td className="px-4 py-3">
                      <EntityIdChip id={g.access_profile_id} ref={profiles.find((p) => p.id === g.access_profile_id)?.name} />
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
              {grants.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-400 dark:text-gray-500">
                    No active grants in scope.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
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
