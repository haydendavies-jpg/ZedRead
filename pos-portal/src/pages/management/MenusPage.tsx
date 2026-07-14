/**
 * Menus — saved, schedulable configurations distinct from a POS MenuLayout
 * (design_handoff_menu_studio/README.md "Screen: Menus"). A Menu optionally
 * points at the MenuLayout (button arrangement) it activates and carries its
 * own draft/scheduled/published lifecycle + brand-or-site assignment.
 */

import { Fragment, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useAuth, isMgmtUser } from '../../context/AuthContext'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { Modal } from '../../components/Modal'
import { EntityIdChip } from '../../components/EntityIdChip'
import { StatusBadge } from '../../components/StatusBadge'
import { apiErrorMessage } from '../../utils/apiError'
import type { Menu, MenuLayout } from '../../types'

export function MenusPage() {
  const qc = useQueryClient()
  const brandId = useMgmtBrandId()
  const [showCreate, setShowCreate] = useState(false)
  const [schedulingId, setSchedulingId] = useState<string | null>(null)
  const [scheduleDraft, setScheduleDraft] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)

  const params = brandId ? { brand_id: brandId } : {}

  const { data: menus = [], isLoading } = useQuery<Menu[]>({
    queryKey: ['menus', brandId],
    queryFn: () => api.get('/menus', { params: { ...params, limit: 200 } }).then((r) => r.data),
    enabled: !!brandId,
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['menus', brandId] })
  const onActionError = (e: unknown) => setActionError(apiErrorMessage(e, 'Action failed.'))

  const duplicate = useMutation({
    mutationFn: (id: string) => api.post(`/menus/${id}/duplicate`, {}, { params }),
    onSuccess: invalidate,
    onError: onActionError,
  })
  const publish = useMutation({
    mutationFn: (id: string) => api.post(`/menus/${id}/publish`, {}, { params }),
    onSuccess: invalidate,
    onError: onActionError,
  })
  const cancelSchedule = useMutation({
    mutationFn: (id: string) => api.post(`/menus/${id}/cancel-schedule`, {}, { params }),
    onSuccess: invalidate,
    onError: onActionError,
  })
  const schedule = useMutation({
    mutationFn: ({ id, scheduledAt }: { id: string; scheduledAt: string }) =>
      api.post(`/menus/${id}/schedule`, { scheduled_at: new Date(scheduledAt).toISOString() }, { params }),
    onSuccess: () => { invalidate(); setSchedulingId(null); setScheduleDraft('') },
    onError: onActionError,
  })

  if (!brandId) {
    return <div className="flex items-center justify-center h-64 text-sm text-gray-400">No brand context available.</div>
  }

  return (
    <div className="p-4 sm:p-6" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h1 className="font-serif font-bold text-[22px] text-gray-900 dark:text-gray-100 leading-tight">Menus</h1>
          <p className="text-[11px] font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500 mt-0.5">
            {menus.length} {menus.length === 1 ? 'menu' : 'menus'}
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-3 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
        >
          + New menu
        </button>
      </div>

      {actionError && (
        <p className="text-sm text-red-600 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2 mb-4">
          {actionError}
        </p>
      )}

      {isLoading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : (
        <div className="zr-table-wrap">
          <table className="zr-table min-w-[820px]">
            <thead>
              <tr>
                <th>Menu</th>
                <th>Status</th>
                <th>Assigned to</th>
                <th>Updated</th>
                <th className="zr-num">Actions</th>
              </tr>
            </thead>
            <tbody>
              {menus.map((m) => (
                <Fragment key={m.id}>
                  <tr>
                    <td className="px-4 py-3">
                      <div className="font-semibold text-gray-900 dark:text-gray-100">{m.name}</div>
                      {m.note && <div className="text-xs text-gray-400 dark:text-gray-500">{m.note}</div>}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={m.status} />
                      {m.status === 'scheduled' && m.scheduled_at && (
                        <span className="ml-2 text-xs text-gray-400 dark:text-gray-500">
                          {new Date(m.scheduled_at).toLocaleString()}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                      {m.scope === 'brand' ? 'All sites' : m.site_id ? <EntityIdChip id={m.site_id} /> : '—'}
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                      {new Date(m.updated_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end flex-wrap gap-1.5">
                        {m.status === 'draft' && (
                          <>
                            <button onClick={() => publish.mutate(m.id)} className="px-2.5 py-1.5 bg-brand-600 text-white text-xs font-semibold rounded-md hover:bg-brand-700">
                              Publish
                            </button>
                            <button
                              onClick={() => { setSchedulingId(m.id); setScheduleDraft('') }}
                              className="px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-semibold text-gray-600 dark:text-gray-300 rounded-md"
                            >
                              ◷ Schedule
                            </button>
                          </>
                        )}
                        {m.status === 'scheduled' && (
                          <>
                            <button onClick={() => publish.mutate(m.id)} className="px-2.5 py-1.5 bg-brand-600 text-white text-xs font-semibold rounded-md hover:bg-brand-700">
                              Publish now
                            </button>
                            <button onClick={() => cancelSchedule.mutate(m.id)} className="px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-semibold text-gray-600 dark:text-gray-300 rounded-md">
                              Cancel
                            </button>
                          </>
                        )}
                        <button onClick={() => duplicate.mutate(m.id)} className="px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-semibold text-gray-600 dark:text-gray-300 rounded-md">
                          ⧉ Duplicate
                        </button>
                      </div>
                    </td>
                  </tr>
                  {schedulingId === m.id && (
                    <tr className="bg-brand-50/60 dark:bg-brand-950/30">
                      <td colSpan={5} className="px-4 py-3">
                        <div className="flex flex-wrap items-center gap-3">
                          <span className="text-[11px] font-semibold uppercase tracking-wide text-brand-600 dark:text-brand-400">Schedule publish</span>
                          <input
                            type="datetime-local"
                            value={scheduleDraft}
                            onChange={(e) => setScheduleDraft(e.target.value)}
                            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 rounded-lg text-sm"
                          />
                          <div className="flex-1" />
                          <button onClick={() => setSchedulingId(null)} className="text-xs font-medium text-gray-500 dark:text-gray-400">
                            Cancel
                          </button>
                          <button
                            onClick={() => { if (scheduleDraft) schedule.mutate({ id: m.id, scheduledAt: scheduleDraft }) }}
                            disabled={!scheduleDraft || schedule.isPending}
                            className="px-3 py-1.5 bg-brand-600 text-white text-xs font-semibold rounded-lg disabled:opacity-50"
                          >
                            Schedule publish
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
              {menus.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-400">No menus yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <MenuCreateModal
          brandId={brandId}
          onClose={() => setShowCreate(false)}
          onSaved={() => { invalidate(); setShowCreate(false) }}
        />
      )}
    </div>
  )
}

function MenuCreateModal({ brandId, onClose, onSaved }: { brandId: string; onClose: () => void; onSaved: () => void }) {
  const { user } = useAuth()
  const mgmtSiteId = isMgmtUser(user) && user.scope === 'site' ? user.site_id ?? null : null

  const [name, setName] = useState('')
  const [note, setNote] = useState('')
  const [scope, setScope] = useState<'brand' | 'site'>(mgmtSiteId ? 'site' : 'brand')
  const [siteId, setSiteId] = useState(mgmtSiteId ?? '')
  const [menuLayoutId, setMenuLayoutId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const params = { brand_id: brandId }
  const { data: layouts = [] } = useQuery<MenuLayout[]>({
    queryKey: ['menu-layouts', brandId],
    queryFn: () => api.get('/menu-layouts', { params }).then((r) => r.data),
  })

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await api.post(
        '/menus',
        {
          name,
          note: note || null,
          scope,
          site_id: scope === 'site' ? siteId : null,
          menu_layout_id: menuLayoutId || null,
        },
        { params },
      )
      onSaved()
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'Failed to create menu.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="New menu" onClose={onClose}>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Note (optional)</label>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. Primary in-store menu"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">POS layout (optional)</label>
          <select
            value={menuLayoutId}
            onChange={(e) => setMenuLayoutId(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="">None</option>
            {layouts.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Assigned to</label>
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value as 'brand' | 'site')}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="brand">All sites</option>
            <option value="site">One site</option>
          </select>
        </div>
        {scope === 'site' && !mgmtSiteId && (
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Site ID</label>
            <input
              value={siteId}
              onChange={(e) => setSiteId(e.target.value)}
              placeholder="Site UUID"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
        )}
        {error && (
          <p className="text-sm text-red-600 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100">
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !name || (scope === 'site' && !siteId)}
            className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
