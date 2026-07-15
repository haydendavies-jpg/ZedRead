/**
 * Permission Scopes page (Stage 18) — portal UI for the Stage 15 page-permission
 * system: pick an access profile, toggle which pages it grants.
 *
 * License-gated pages are never hidden — where a site context is available
 * (SuperAdmin preview picker, or a site-scope management user's own site) a
 * "License-gated" badge explains why a granted page won't actually be visible
 * to a User at that site, without disabling the toggle itself (the grant and
 * the license gate are independent — see ROLE_MODEL.md §4).
 */

import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, fetchAll } from '../../api/axios'
import { useAuth, isMgmtUser, isSuperAdmin } from '../../context/AuthContext'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { ScopeGuard } from '../../components/ScopeGuard'
import {
  PAGE_CATALOG,
  PAGE_CATEGORY_LABELS,
  type PageCategory,
  type PagePermissionsResponse,
  type VisiblePagesResponse,
  type Site,
} from '../../types'

interface AccessProfileOption {
  id: string
  name: string
  is_system: boolean
}

async function fetchProfiles(brandId: string): Promise<AccessProfileOption[]> {
  return fetchAll<AccessProfileOption>('/access-profiles', { brand_id: brandId })
}

const CATEGORIES = Array.from(new Set(PAGE_CATALOG.map((p) => p.category))) as PageCategory[]

export function AccessProfilesPage() {
  return (
    <ScopeGuard minScope="brand">
      <AccessProfilesPageInner />
    </ScopeGuard>
  )
}

function AccessProfilesPageInner() {
  const qc = useQueryClient()
  const brandId = useMgmtBrandId()
  const { user } = useAuth()
  const mgmtUser = isMgmtUser(user) ? user : null
  const superAdmin = isSuperAdmin(user) ? user : null

  const { data: profiles = [], isLoading: profilesLoading } = useQuery<AccessProfileOption[]>({
    queryKey: ['access-profiles', brandId],
    queryFn: () => fetchProfiles(brandId!),
    enabled: !!brandId,
  })

  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null)
  const activeProfileId = selectedProfileId ?? profiles[0]?.id ?? null

  // Only a SuperAdmin can list a brand's sites (/sites is portal-admin-only),
  // so only they get a site picker for the license-gate preview. A site-scope
  // management user already has one site (from the JWT); brand/group-scope
  // management users have no route to resolve a specific site at all — the
  // preview is simply unavailable to them, not faked.
  const { data: sites = [] } = useQuery<Site[]>({
    queryKey: ['sites-for-license-preview', brandId],
    queryFn: () => fetchAll<Site>('/sites', { brand_id: brandId }),
    enabled: !!brandId && !!superAdmin,
  })

  const [previewSiteId, setPreviewSiteId] = useState<string>('')
  const resolvedSiteId = superAdmin
    ? previewSiteId || sites[0]?.id || ''
    : mgmtUser?.scope === 'site'
      ? mgmtUser.site_id ?? ''
      : ''

  const { data: granted = [], isLoading: pagesLoading } = useQuery<string[]>({
    queryKey: ['access-profile-pages', activeProfileId],
    queryFn: () =>
      api
        .get<PagePermissionsResponse>(`/access-profiles/${activeProfileId}/pages`)
        .then((r) => r.data.page_keys),
    enabled: !!activeProfileId,
  })

  const { data: visible } = useQuery<string[]>({
    queryKey: ['access-profile-visible-pages', activeProfileId, resolvedSiteId],
    queryFn: () =>
      api
        .get<VisiblePagesResponse>(`/access-profiles/${activeProfileId}/visible-pages`, {
          params: { site_id: resolvedSiteId },
        })
        .then((r) => r.data.page_keys),
    enabled: !!activeProfileId && !!resolvedSiteId,
  })

  // A granted page that isn't in the resolved visible set is blocked purely by
  // the site's license plan (visible-pages ANDs the grant with the license
  // gate). Ungranted pages have no license verdict available this way — that
  // asymmetry is fine, since an ungranted page has nothing to warn about yet.
  const licenseBlocked = useMemo(() => {
    if (!visible) return new Set<string>()
    return new Set(granted.filter((k) => !visible.includes(k)))
  }, [granted, visible])

  const invalidatePages = () => qc.invalidateQueries({ queryKey: ['access-profile-pages', activeProfileId] })

  const grant = useMutation({
    mutationFn: (pageKey: string) => api.post(`/access-profiles/${activeProfileId}/pages`, { page_key: pageKey }),
    onSuccess: invalidatePages,
    onError: invalidatePages,
  })
  const revoke = useMutation({
    mutationFn: (pageKey: string) => api.delete(`/access-profiles/${activeProfileId}/pages/${pageKey}`),
    onSuccess: invalidatePages,
    onError: invalidatePages,
  })

  const toggle = (pageKey: string, isGranted: boolean) => {
    if (!activeProfileId) return
    if (isGranted) revoke.mutate(pageKey)
    else grant.mutate(pageKey)
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
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Permission Scopes</h1>
        {superAdmin && sites.length > 0 && (
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Preview site (license gate)</label>
            <select
              value={resolvedSiteId}
              onChange={(e) => setPreviewSiteId(e.target.value)}
              className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              {sites.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {!resolvedSiteId && (
        <p className="text-xs text-gray-400 dark:text-gray-500 mb-4">
          License-plan gating preview isn't available at your scope — grants below still take
          effect, but whether a page is actually visible to a User also depends on their site's
          license plan.
        </p>
      )}

      {profilesLoading ? (
        <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
      ) : (
        <div className="flex flex-wrap gap-2 mb-6">
          {profiles.map((p) => (
            <button
              key={p.id}
              onClick={() => setSelectedProfileId(p.id)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                activeProfileId === p.id
                  ? 'bg-brand-50 border-brand-200 text-brand-800'
                  : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/60'
              }`}
            >
              {p.name}
            </button>
          ))}
          {profiles.length === 0 && <p className="text-sm text-gray-400 dark:text-gray-500">No access profiles yet.</p>}
        </div>
      )}

      {activeProfileId && (
        pagesLoading ? (
          <p className="text-sm text-gray-400 dark:text-gray-500">Loading permissions…</p>
        ) : (
          <div className="space-y-6">
            {CATEGORIES.map((category) => (
              <div key={category}>
                <h2 className="text-xs font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wide mb-2">
                  {PAGE_CATEGORY_LABELS[category]}
                </h2>
                <div className="zr-table-wrap">
                  <table className="zr-table min-w-[400px]">
                    <tbody>
                      {PAGE_CATALOG.filter((p) => p.category === category).map((p) => {
                        const isGranted = granted.includes(p.key)
                        const isLicenseBlocked = licenseBlocked.has(p.key)
                        return (
                          <tr key={p.key}>
                            <td className="px-4 py-3">
                              <label className="flex items-center gap-2 cursor-pointer">
                                <input
                                  type="checkbox"
                                  checked={isGranted}
                                  disabled={grant.isPending || revoke.isPending}
                                  onChange={() => toggle(p.key, isGranted)}
                                  className="rounded border-gray-300 dark:border-gray-600 text-brand-600 focus:ring-brand-500"
                                />
                                <span className="text-gray-900 dark:text-gray-100">{p.label}</span>
                              </label>
                            </td>
                            <td className="px-4 py-3 text-right">
                              {isLicenseBlocked && (
                                <span
                                  title="Granted by role, but this site's license plan doesn't include this page"
                                  className="inline-block px-2 py-0.5 rounded-full text-xs bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400"
                                >
                                  License-gated
                                </span>
                              )}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  )
}
