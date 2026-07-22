/**
 * Management-portal Settings page — search/edit brand- and site-level POS
 * setting overrides (Android POS Phase 2 settings framework).
 *
 * The catalog of valid settings is code-defined on the backend
 * (app/constants/settings.py); this page only ever reads/writes overrides.
 * A brand-scope caller edits the brand-level default; a site-scope caller
 * (or a brand/group-scope caller who picks a site) edits that site's own
 * override, which wins over the brand default on the POS terminal.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, fetchAll } from '../../api/axios'
import { useAuth, isMgmtUser } from '../../context/AuthContext'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import type { Setting, Site } from '../../types'

function ValueBadge({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-[var(--zr-faint)] text-xs">Not set</span>
  }
  if (typeof value === 'boolean') {
    return <span className={`zr-pill zr-pill--${value ? 'live' : 'void'}`}>{value ? 'On' : 'Off'}</span>
  }
  if (Array.isArray(value)) {
    return <span className="text-xs">{value.join(', ') || '—'}</span>
  }
  return <span className="text-xs">{String(value)}</span>
}

function SettingEditor({
  setting,
  onSave,
  onCancel,
  saving,
}: {
  setting: Setting
  onSave: (value: unknown) => void
  onCancel: () => void
  saving: boolean
}) {
  const initial = setting.site_value ?? setting.brand_value ?? setting.default_value
  const [draft, setDraft] = useState<unknown>(initial)

  return (
    <div className="flex flex-wrap items-center gap-2">
      {setting.type === 'boolean' && (
        <select
          value={draft ? 'true' : 'false'}
          onChange={(e) => setDraft(e.target.value === 'true')}
          className="px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-lg text-xs bg-white dark:bg-gray-800"
        >
          <option value="true">On</option>
          <option value="false">Off</option>
        </select>
      )}
      {setting.type === 'single_select' && (
        <select
          value={(draft as string) ?? ''}
          onChange={(e) => setDraft(e.target.value)}
          className="px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-lg text-xs bg-white dark:bg-gray-800"
        >
          {(setting.options ?? []).map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
      )}
      {setting.type === 'multi_select' && (
        <div className="flex flex-wrap gap-2">
          {(setting.options ?? []).map((o) => {
            const list = (draft as string[]) ?? []
            const checked = list.includes(o)
            return (
              <label key={o} className="flex items-center gap-1 text-xs">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => {
                    setDraft(e.target.checked ? [...list, o] : list.filter((v) => v !== o))
                  }}
                />
                {o}
              </label>
            )
          })}
        </div>
      )}
      {setting.type === 'datetime' && (
        <input
          type="datetime-local"
          value={(draft as string) ?? ''}
          onChange={(e) => setDraft(e.target.value)}
          className="px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-lg text-xs bg-white dark:bg-gray-800"
        />
      )}
      <button
        onClick={() => onSave(draft)}
        disabled={saving}
        className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-xs font-medium px-2 py-1 rounded-lg transition-colors"
      >
        Save
      </button>
      <button onClick={onCancel} className="text-xs text-[var(--zr-muted)] hover:underline">
        Cancel
      </button>
    </div>
  )
}

export function SettingsPage() {
  const qc = useQueryClient()
  const { user } = useAuth()
  const brandId = useMgmtBrandId()
  const mgmtUser = isMgmtUser(user) ? user : null
  const fixedSiteId = mgmtUser?.site_id ?? null

  const [selectedSiteId, setSelectedSiteId] = useState('')
  const [search, setSearch] = useState('')
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const siteId = fixedSiteId ?? selectedSiteId

  const needsSiteSelector = !fixedSiteId && !!brandId
  const { data: sites = [] } = useQuery<Site[]>({
    queryKey: ['sites-for-brand', brandId],
    queryFn: () => fetchAll<Site>('/sites', { brand_id: brandId }),
    enabled: needsSiteSelector,
  })

  const queryParams: Record<string, string> = {}
  if (brandId) queryParams.brand_id = brandId
  if (siteId) queryParams.site_id = siteId
  if (search) queryParams.search = search

  const {
    data: settings = [],
    isLoading,
    error,
  } = useQuery<Setting[]>({
    queryKey: ['settings', queryParams],
    queryFn: async () => (await api.get('/settings', { params: queryParams })).data,
    enabled: !!brandId || !!fixedSiteId,
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['settings'] })

  const saveMutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) =>
      api.put(`/settings/${key}`, { value, site_id: siteId || null }, { params: brandId ? { brand_id: brandId } : {} }),
    onSuccess: () => {
      setActionError(null)
      setEditingKey(null)
      invalidate()
    },
    onError: (e: unknown) => {
      invalidate()
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setActionError(msg ?? 'Failed to save setting.')
    },
  })

  const resetMutation = useMutation({
    mutationFn: (key: string) =>
      api.delete(`/settings/${key}`, {
        params: { site_id: siteId || undefined, brand_id: brandId || undefined },
      }),
    onSuccess: () => {
      setActionError(null)
      invalidate()
    },
    onError: (e: unknown) => {
      invalidate()
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setActionError(msg ?? 'Failed to reset setting.')
    },
  })

  const siteName = (id: string) => sites.find((s) => s.id === id)?.name ?? id.slice(0, 8)

  if (!brandId && !fixedSiteId) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-gray-400 dark:text-gray-500">
        No brand or site context available.
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold font-serif text-gray-900 dark:text-gray-100">Settings</h1>
      </div>

      {actionError && <p className="text-sm text-red-600">{actionError}</p>}

      <div className="flex flex-wrap items-end gap-3">
        {needsSiteSelector && (
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Site</label>
            <select
              value={selectedSiteId}
              onChange={(e) => setSelectedSiteId(e.target.value)}
              className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white dark:bg-gray-800"
            >
              <option value="">Brand default only</option>
              {sites.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
        )}
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Search</label>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Name, label, or category…"
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white dark:bg-gray-800"
          />
        </div>
        <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto pb-2">{settings.length} settings</span>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
      ) : error ? (
        <p className="text-sm text-red-500">Failed to load settings.</p>
      ) : (
        <div className="zr-table-wrap">
          <table className="zr-table min-w-[820px]">
            <thead>
              <tr>
                <th>Setting</th>
                <th>Category</th>
                <th>Brand default</th>
                {siteId && <th>{siteName(siteId)} override</th>}
                <th>Effective</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {settings.map((s) => (
                <tr key={s.key}>
                  <td className="font-medium">
                    {s.label}
                    <div className="text-[10px] text-[var(--zr-faint)] font-mono">{s.key}</div>
                  </td>
                  <td className="text-[var(--zr-muted)]">{s.category}</td>
                  <td><ValueBadge value={s.brand_value ?? s.default_value} /></td>
                  {siteId && <td><ValueBadge value={s.site_value} /></td>}
                  <td className="font-medium"><ValueBadge value={s.effective_value} /></td>
                  <td className="zr-cell-pad">
                    {editingKey === s.key ? (
                      <SettingEditor
                        setting={s}
                        saving={saveMutation.isPending}
                        onSave={(value) => saveMutation.mutate({ key: s.key, value })}
                        onCancel={() => setEditingKey(null)}
                      />
                    ) : (
                      <div className="flex items-center gap-3">
                        <button onClick={() => setEditingKey(s.key)} className="text-brand-600 hover:underline text-xs">
                          Edit {siteId ? 'site' : 'brand'} value
                        </button>
                        {(siteId ? s.site_value : s.brand_value) != null && (
                          <button
                            onClick={() => resetMutation.mutate(s.key)}
                            disabled={resetMutation.isPending}
                            className="text-red-600 hover:underline text-xs disabled:opacity-50"
                          >
                            Reset
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {settings.length === 0 && (
                <tr>
                  <td colSpan={siteId ? 6 : 5} className="text-center text-[var(--zr-faint)] py-8">
                    No settings match the current search.
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
