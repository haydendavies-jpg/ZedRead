/** POS user access grants management page — list and revoke grants in scope. */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { EntityIdChip } from '../../components/EntityIdChip'
import { ScopeGuard } from '../../components/ScopeGuard'
import type { AccessGrant } from '../../types'

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

  const params = brandId ? { brand_id: brandId } : {}

  const { data: grants = [], isLoading } = useQuery<AccessGrant[]>({
    queryKey: ['access-grants', brandId],
    queryFn: () => api.get('/access-grants', { params }).then((r) => r.data),
    enabled: brandId !== undefined,
  })

  const revoke = useMutation({
    mutationFn: (id: string) => api.delete(`/access-grants/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['access-grants', brandId] }),
  })

  if (!brandId) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-gray-400">
        No brand context available.
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Users &amp; Grants</h1>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm min-w-[500px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">User ID</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Scope</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Entity ID</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Profile</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {grants.map((g) => {
                const entityId = g.site_id ?? g.brand_id ?? g.group_id ?? ''
                return (
                  <tr key={g.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <EntityIdChip id={g.user_id} />
                    </td>
                    <td className="px-4 py-3 text-gray-700 capitalize">{g.scope}</td>
                    <td className="px-4 py-3">
                      {entityId && <EntityIdChip id={entityId} />}
                    </td>
                    <td className="px-4 py-3">
                      <EntityIdChip id={g.access_profile_id} />
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
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                    No active grants in scope.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
