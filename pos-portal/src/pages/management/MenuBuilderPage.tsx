/**
 * POS Layout grid editor (Menu Studio redesign, Phase 2) — replaces the
 * Stage 23 prototype's single-level, HTML5-drag-and-drop tab/button list
 * with the design handoff's graphical editor: a rail of top-level tabs,
 * a 6-column dense CSS grid of resizable/movable tiles (product or folder
 * buttons), pointer-based select/multi-select/drag-move/resize, a
 * multi-select floating action bar, and a single-selection inspector panel.
 *
 * Folder buttons open a nested MenuTab (menu_tabs.parent_tab_id) — nesting
 * is unbounded, though the editor only ever shows one tab's tiles at a time
 * and a breadcrumb built by walking parent_tab_id back to a top-level tab.
 */

import { Fragment, useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, fetchAll } from '../../api/axios'
import { useAuth, isMgmtUser } from '../../context/AuthContext'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { Modal } from '../../components/Modal'
import { MENU_STUDIO_PALETTE, textColorOn, centsToDisplay } from '../../utils/menuStudio'
import { apiErrorMessage } from '../../utils/apiError'
import type { MenuButton, MenuLayout, MenuLayoutDetail, MenuTab, ProductListItem, PublishResult, PublishWarning } from '../../types'

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function formatDays(activeDays: number[]): string {
  const sorted = [...activeDays].sort((a, b) => a - b)
  if (sorted.length === 7) return 'Every day'
  if (sorted.length === 5 && sorted.every((d, i) => d === i)) return 'Mon–Fri'
  if (sorted.length === 2 && sorted[0] === 5 && sorted[1] === 6) return 'Sat–Sun'
  return sorted.map((d) => DAY_LABELS[d]).join(', ')
}

function formatTimeLabel(t: string | null): string {
  if (!t) return ''
  const [h, m] = t.split(':').map(Number)
  const period = h >= 12 ? 'PM' : 'AM'
  const h12 = h % 12 === 0 ? 12 : h % 12
  return `${h12}:${String(m).padStart(2, '0')} ${period}`
}

function activeTimeLabel(layout: MenuLayout): string {
  return layout.is_all_day ? 'All day' : `${formatTimeLabel(layout.start_time)} – ${formatTimeLabel(layout.end_time)}`
}

export function MenuBuilderPage() {
  const brandId = useMgmtBrandId()
  const [selectedLayoutId, setSelectedLayoutId] = useState<string | null>(null)

  if (!brandId) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-gray-400 dark:text-gray-500">
        No brand context available.
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 space-y-4" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      {selectedLayoutId ? (
        <GridEditor brandId={brandId} layoutId={selectedLayoutId} onBack={() => setSelectedLayoutId(null)} />
      ) : (
        <LayoutsList brandId={brandId} onOpen={setSelectedLayoutId} />
      )}
    </div>
  )
}

// ── Layouts list ─────────────────────────────────────────────────────────────

function LayoutsList({ brandId, onOpen }: { brandId: string; onOpen: (id: string) => void }) {
  const qc = useQueryClient()
  const params = { brand_id: brandId }
  const [showCreate, setShowCreate] = useState(false)
  const [hoursLayout, setHoursLayout] = useState<MenuLayout | null>(null)
  const [schedulingId, setSchedulingId] = useState<string | null>(null)
  const [scheduleDraft, setScheduleDraft] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)

  const { data: layouts = [], isLoading } = useQuery<MenuLayout[]>({
    queryKey: ['menu-layouts', brandId],
    queryFn: () => fetchAll<MenuLayout>('/menu-layouts', params),
  })

  const invalidateList = () => qc.invalidateQueries({ queryKey: ['menu-layouts', brandId] })
  const onActionError = (e: unknown) => { invalidateList(); setActionError(apiErrorMessage(e, 'Action failed.')) }

  const publish = useMutation({
    mutationFn: (layout: MenuLayout) => api.post(`/menu-layouts/${layout.id}/publish`, {}, { params }),
    onSuccess: invalidateList,
    onError: onActionError,
  })
  const unpublish = useMutation({
    mutationFn: (layout: MenuLayout) => api.post(`/menu-layouts/${layout.id}/unpublish`, {}, { params }),
    onSuccess: invalidateList,
    onError: onActionError,
  })
  const remove = useMutation({
    mutationFn: (layout: MenuLayout) => api.delete(`/menu-layouts/${layout.id}`, { params }),
    onSuccess: invalidateList,
    onError: onActionError,
  })
  const duplicate = useMutation({
    mutationFn: (layout: MenuLayout) => api.post(`/menu-layouts/${layout.id}/duplicate`, {}, { params }),
    onSuccess: invalidateList,
    onError: onActionError,
  })
  const schedule = useMutation({
    mutationFn: ({ id, scheduledAt }: { id: string; scheduledAt: string }) =>
      api.post(`/menu-layouts/${id}/schedule-publish`, { scheduled_publish_at: new Date(scheduledAt).toISOString() }, { params }),
    onSuccess: () => { invalidateList(); setSchedulingId(null); setScheduleDraft('') },
    onError: onActionError,
  })
  const cancelSchedule = useMutation({
    mutationFn: (id: string) => api.post(`/menu-layouts/${id}/cancel-schedule-publish`, {}, { params }),
    onSuccess: invalidateList,
    onError: onActionError,
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-serif font-bold text-[22px] text-gray-900 dark:text-gray-100 leading-tight">POS Layouts</h1>
          <p className="text-[11px] font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500 mt-0.5">
            {layouts.length} {layouts.length === 1 ? 'layout' : 'layouts'}
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-3 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
        >
          + New layout
        </button>
      </div>

      {actionError && (
        <p className="text-sm text-red-600 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">
          {actionError}
        </p>
      )}

      {isLoading ? (
        <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
      ) : (
        <div className="zr-table-wrap">
          <table className="zr-table min-w-[860px]">
            <thead>
              <tr>
                <th>Layout</th>
                <th>Status</th>
                <th>Active time</th>
                <th>Last published</th>
                <th>Last edited</th>
                <th className="zr-num">Actions</th>
              </tr>
            </thead>
            <tbody>
              {layouts.map((layout) => (
                <Fragment key={layout.id}>
                <tr className="hover:bg-gray-50 dark:hover:bg-gray-800/60 cursor-pointer" onClick={() => onOpen(layout.id)}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: layout.color }} />
                      <div className="min-w-0">
                        <div className="font-semibold text-gray-900 dark:text-gray-100 truncate">{layout.name}</div>
                        <div className="text-xs text-gray-400 dark:text-gray-500">{layout.button_count} buttons</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`zr-pill ${layout.is_published ? 'zr-pill--live' : 'zr-pill--draft'}`}>
                      {layout.is_published ? 'Published' : 'Unpublished'}
                    </span>
                    {layout.scheduled_publish_at && (
                      <div className="text-[11px] text-gray-400 dark:text-gray-500 mt-1">
                        Scheduled {new Date(layout.scheduled_publish_at).toLocaleString()}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-col gap-0.5 min-w-0">
                      <span className="font-mono text-xs text-gray-700 dark:text-gray-300">{activeTimeLabel(layout)}</span>
                      <span className="text-[11px] text-gray-400 dark:text-gray-500">{formatDays(layout.active_days)}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                    {layout.published_at ? (
                      <>
                        <div>{new Date(layout.published_at).toLocaleDateString()}</div>
                        <div className="text-[11px] text-gray-400 dark:text-gray-500">{new Date(layout.published_at).toLocaleTimeString()}</div>
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                    <div>{new Date(layout.updated_at).toLocaleDateString()}</div>
                    <div className="text-[11px] text-gray-400 dark:text-gray-500">{new Date(layout.updated_at).toLocaleTimeString()}</div>
                  </td>
                  <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-end flex-wrap gap-1.5">
                      <button onClick={() => onOpen(layout.id)} className="px-2.5 py-1.5 bg-brand-600 text-white text-xs font-semibold rounded-md hover:bg-brand-700">
                        Edit
                      </button>
                      <button
                        onClick={() => (layout.is_published ? unpublish.mutate(layout) : publish.mutate(layout))}
                        className="px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-semibold text-gray-600 dark:text-gray-300 rounded-md"
                      >
                        {layout.is_published ? 'Unpublish' : 'Publish'}
                      </button>
                      <button onClick={() => setHoursLayout(layout)} className="px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-semibold text-gray-600 dark:text-gray-300 rounded-md">
                        ◷ Hours
                      </button>
                      {layout.scheduled_publish_at ? (
                        <button onClick={() => cancelSchedule.mutate(layout.id)} className="px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-semibold text-gray-600 dark:text-gray-300 rounded-md">
                          Cancel schedule
                        </button>
                      ) : (
                        <button
                          onClick={() => { setSchedulingId(layout.id); setScheduleDraft('') }}
                          className="px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-semibold text-gray-600 dark:text-gray-300 rounded-md"
                        >
                          Schedule publish
                        </button>
                      )}
                      <button onClick={() => duplicate.mutate(layout)} className="px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-semibold text-gray-600 dark:text-gray-300 rounded-md">
                        ⧉ Duplicate
                      </button>
                      <button
                        onClick={() => { if (confirm(`Delete layout "${layout.name}"?`)) remove.mutate(layout) }}
                        className="px-2.5 py-1.5 border border-red-200 dark:border-red-800 text-xs font-semibold text-red-600 dark:text-red-400 rounded-md"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
                {schedulingId === layout.id && (
                  <tr className="bg-brand-50/60 dark:bg-brand-950/30">
                    <td colSpan={6} className="px-4 py-3">
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
                          onClick={() => { if (scheduleDraft) schedule.mutate({ id: layout.id, scheduledAt: scheduleDraft }) }}
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
              {layouts.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-400 dark:text-gray-500">
                    No POS layouts yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <CreateLayoutModal
          brandId={brandId}
          onClose={() => setShowCreate(false)}
          onSaved={(id) => { invalidateList(); setShowCreate(false); onOpen(id) }}
        />
      )}
      {hoursLayout && (
        <ActiveHoursModal
          brandId={brandId}
          layout={hoursLayout}
          onClose={() => setHoursLayout(null)}
          onSaved={() => { invalidateList(); setHoursLayout(null) }}
        />
      )}
    </div>
  )
}

function CreateLayoutModal({
  brandId,
  onClose,
  onSaved,
}: {
  brandId: string
  onClose: () => void
  onSaved: (id: string) => void
}) {
  const { user } = useAuth()
  const mgmtSiteId = isMgmtUser(user) && user.scope === 'site' ? user.site_id ?? null : null

  const [name, setName] = useState('')
  const [color, setColor] = useState('#A82040')
  const [scope, setScope] = useState<'brand' | 'site'>('brand')
  const [siteId, setSiteId] = useState(mgmtSiteId ?? '')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const resp = await api.post(
        '/menu-layouts',
        { name, color, scope, site_id: scope === 'site' ? siteId : null },
        { params: { brand_id: brandId } }
      )
      onSaved(resp.data.id)
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'Failed to create layout.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="Add POS layout" onClose={onClose}>
      <div className="space-y-4">
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Café — All Day, Breakfast"
              autoFocus
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Colour</label>
            <div className="flex flex-wrap gap-1.5">
              {MENU_STUDIO_PALETTE.slice(0, 5).map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  className={`w-7 h-7 rounded-md border-2 ${color === c ? 'border-gray-900 dark:border-gray-100' : 'border-transparent'}`}
                  style={{ background: c }}
                />
              ))}
            </div>
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Scope</label>
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value as 'brand' | 'site')}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="brand">All sites in this brand</option>
            <option value="site">A single site</option>
          </select>
        </div>
        {scope === 'site' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Site ID</label>
            {mgmtSiteId ? (
              <input value={siteId} disabled className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 rounded-lg text-sm text-gray-500 dark:text-gray-400" />
            ) : (
              <>
                <input
                  value={siteId}
                  onChange={(e) => setSiteId(e.target.value)}
                  placeholder="Paste the site's UUID"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                  No site picker is available at your access level yet — copy the site's ID from its detail page.
                </p>
              </>
            )}
          </div>
        )}
        {error && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900">
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

function ActiveHoursModal({
  brandId,
  layout,
  onClose,
  onSaved,
}: {
  brandId: string
  layout: MenuLayout
  onClose: () => void
  onSaved: () => void
}) {
  const [isAllDay, setIsAllDay] = useState(layout.is_all_day)
  const [startTime, setStartTime] = useState(layout.start_time?.slice(0, 5) ?? '07:00')
  const [endTime, setEndTime] = useState(layout.end_time?.slice(0, 5) ?? '11:00')
  const [activeDays, setActiveDays] = useState<number[]>(layout.active_days)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const toggleDay = (d: number) => setActiveDays((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort((a, b) => a - b)))

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await api.patch(
        `/menu-layouts/${layout.id}`,
        {
          is_all_day: isAllDay,
          start_time: isAllDay ? null : `${startTime}:00`,
          end_time: isAllDay ? null : `${endTime}:00`,
          active_days: activeDays,
        },
        { params: { brand_id: brandId } }
      )
      onSaved()
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'Failed to update active hours.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title={`Active hours — ${layout.name}`} onClose={onClose}>
      <div className="space-y-4">
        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
          <input type="checkbox" checked={isAllDay} onChange={(e) => setIsAllDay(e.target.checked)} />
          Visible all day
        </label>
        {!isAllDay && (
          <div className="flex items-end gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Start time</label>
              <input
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">End time</label>
              <input
                type="time"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
          </div>
        )}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Active days</label>
          <div className="flex flex-wrap gap-1.5">
            {DAY_LABELS.map((label, i) => (
              <button
                key={label}
                type="button"
                onClick={() => toggleDay(i)}
                className={`px-2.5 py-1 rounded-full text-xs font-semibold border ${
                  activeDays.includes(i)
                    ? 'bg-brand-600 border-brand-600 text-white'
                    : 'border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {error && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900">
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || (!isAllDay && (!startTime || !endTime)) || activeDays.length === 0}
            className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

// ── Grid editor ──────────────────────────────────────────────────────────────

// A drag can end over a rail tab / folder tile ('tab' — move the selection
// into that tab, appended at the end) or over an empty dashed "+" grid cell
// ('cell' — place the single dragged button at that exact col/row via the
// /place endpoint; see placeSelectionAtCell for the multi-select fallback).
type DropTarget = { kind: 'tab'; tabId: string } | { kind: 'cell'; tabId: string; gridCol: number; gridRow: number }

function parseDropAttr(attr: string | null): DropTarget | null {
  if (!attr) return null
  const parts = attr.split(':')
  if (parts[0] === 'tab' && parts[1]) return { kind: 'tab', tabId: parts[1] }
  if (parts[0] === 'cell' && parts.length === 4) {
    const [, tabId, col, row] = parts
    return { kind: 'cell', tabId, gridCol: Number(col), gridRow: Number(row) }
  }
  return null
}

function GridEditor({ brandId, layoutId, onBack }: { brandId: string; layoutId: string; onBack: () => void }) {
  const qc = useQueryClient()
  const params = { brand_id: brandId }
  const gridRef = useRef<HTMLDivElement>(null)

  const [currentTabId, setCurrentTabId] = useState<string | null>(null)
  const [selected, setSelectedState] = useState<Set<string>>(new Set())
  // Mirrors `selected`, updated synchronously (never via a setState updater,
  // which StrictMode double-invokes) on every setSelected call — so the
  // pointer-drag handler's `pointerup` listener, registered once per press
  // and possibly firing several renders after the selection last changed,
  // can read the *latest* selection without waiting on React's commit.
  // Only read inside event handlers, never during render (see setSelected).
  const selectedRef = useRef<Set<string>>(selected)
  const setSelected = (next: Set<string> | ((prev: Set<string>) => Set<string>)) => {
    const resolved = typeof next === 'function' ? next(selectedRef.current) : next
    selectedRef.current = resolved
    setSelectedState(resolved)
  }
  const [moveMenuOpen, setMoveMenuOpen] = useState(false)
  const [warnings, setWarnings] = useState<PublishWarning[] | null>(null)
  const [showHours, setShowHours] = useState(false)
  const [showProductPicker, setShowProductPicker] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [dragPos, setDragPos] = useState({ x: 0, y: 0 })
  const [dragOverTarget, setDragOverTargetState] = useState<DropTarget | null>(null)
  // Same staleness problem as selectedRef above: onUp is a plain window
  // listener closure created once at press-start, so reading the
  // `dragOverTarget` variable directly would see whatever it was at that
  // moment (always null) rather than what onMove last set as the pointer
  // crossed drop targets. Mirror it through a ref for the same reason.
  const dragOverTargetRef = useRef<DropTarget | null>(null)
  const setDragOverTarget = (next: DropTarget | null) => {
    dragOverTargetRef.current = next
    setDragOverTargetState(next)
  }
  // Which specific empty "+" cell was clicked (as opposed to the generic
  // toolbar "+ Product" button) — carried through to addProductButton so the
  // created button can be placed at that exact cell instead of appended.
  const [pendingCell, setPendingCell] = useState<{ col: number; row: number } | null>(null)
  // Insertion index for repositioning within the current tab: while dragging,
  // hovering a tile's left/right edge shows a bar between tiles and dropping
  // there reorders instead of moving into a folder. Ref-mirrored like the two
  // states above (read from the once-registered pointerup listener).
  const [dropIndex, setDropIndexState] = useState<number | null>(null)
  const dropIndexRef = useRef<number | null>(null)
  const setDropIndex = (next: number | null) => {
    dropIndexRef.current = next
    setDropIndexState(next)
  }
  // Extra empty rows added via "+ Row" — per-tab, purely visual (empty slots
  // are not persisted; the grid pads to full rows of 6 and this adds more).
  const [extraRowsByTab, setExtraRowsByTab] = useState<Record<string, number>>({})

  const { data: layout, isLoading } = useQuery<MenuLayoutDetail>({
    queryKey: ['menu-layout', layoutId],
    queryFn: () => api.get(`/menu-layouts/${layoutId}`, { params }).then((r) => r.data),
  })

  const { data: products = [] } = useQuery<ProductListItem[]>({
    queryKey: ['products', brandId],
    queryFn: () => fetchAll<ProductListItem>('/products', params),
  })

  const tabsById = useMemo(() => {
    const map = new Map<string, MenuTab>()
    layout?.tabs.forEach((t) => map.set(t.id, t))
    return map
  }, [layout])

  const topLevelTabs = useMemo(() => (layout?.tabs ?? []).filter((t) => t.parent_tab_id === null), [layout])

  // Falls back to the first top-level tab when nothing is selected yet, or
  // the selected tab was just deleted — derived at render time rather than
  // synced via an effect (no separate "tab was deleted" case to chase).
  const effectiveTabId = currentTabId && tabsById.has(currentTabId) ? currentTabId : topLevelTabs[0]?.id ?? null
  const currentTab = effectiveTabId ? tabsById.get(effectiveTabId) ?? null : null

  const breadcrumb = useMemo(() => {
    const chain: MenuTab[] = []
    let node = currentTab
    while (node) {
      chain.unshift(node)
      node = node.parent_tab_id ? tabsById.get(node.parent_tab_id) ?? null : null
    }
    return chain
  }, [currentTab, tabsById])

  const invalidate = () => qc.invalidateQueries({ queryKey: ['menu-layout', layoutId] })
  const onMutErr = (e: unknown) => { invalidate(); setActionError(apiErrorMessage(e, 'Action failed.')) }

  // ── Cache-patch helpers ──────────────────────────────────────────────────
  // Every mutation below patches the ['menu-layout', layoutId] cache directly
  // from its own response instead of invalidating (which re-fetches the
  // entire tab tree + all buttons + product-ref resolution on every single
  // small edit — the confirmed cause of the reported 5-10s lag). Each
  // response shape was read from the actual route/service code, not assumed.

  /** Patch a single resolved button into whichever tab it now belongs to (button.tab_id), removing any stale copy from other tabs (covers cross-tab moves via /place). */
  const patchButtonMove = (button: MenuButton) => {
    qc.setQueryData<MenuLayoutDetail>(['menu-layout', layoutId], (old) => {
      if (!old) return old
      return {
        ...old,
        tabs: old.tabs.map((t) => {
          const withoutIt = t.buttons.filter((b) => b.id !== button.id)
          if (t.id === button.tab_id) return { ...t, buttons: [...withoutIt, button] }
          return withoutIt.length === t.buttons.length ? t : { ...t, buttons: withoutIt }
        }),
      }
    })
  }

  /** Recursively remove a tab and every descendant tab (parent_tab_id chain) — mirrors the backend's FK cascade for folder-button deletes, computed locally since the whole tab tree is already in cache. */
  const removeTabAndDescendants = (tabs: MenuTab[], rootId: string): MenuTab[] => {
    const toRemove = new Set([rootId])
    let changed = true
    while (changed) {
      changed = false
      for (const t of tabs) {
        if (t.parent_tab_id && toRemove.has(t.parent_tab_id) && !toRemove.has(t.id)) {
          toRemove.add(t.id)
          changed = true
        }
      }
    }
    return tabs.filter((t) => !toRemove.has(t.id))
  }

  const addTab = useMutation({
    mutationFn: (name: string) => api.post<MenuTab>(`/menu-layouts/${layoutId}/tabs`, { name }, { params }),
    onSuccess: (resp) => {
      qc.setQueryData<MenuLayoutDetail>(['menu-layout', layoutId], (old) => (old ? { ...old, tabs: [...old.tabs, resp.data] } : old))
      setCurrentTabId(resp.data.id)
      setSelected(new Set())
    },
    onError: onMutErr,
  })
  const addFolderButton = useMutation({
    mutationFn: ({ tabId, name }: { tabId: string; name: string }) =>
      api.post<MenuButton>(`/menu-layouts/${layoutId}/tabs/${tabId}/buttons`, { kind: 'folder', name }, { params }),
    // The response is the new folder button (with child_tab_id/child_tab_name
    // resolved) but not a full MenuTabOut for the tab it just created — that
    // tab is reconstructed locally (empty buttons array; a brand-new nested
    // tab can't have any yet) rather than refetched.
    onSuccess: (resp, vars) => {
      qc.setQueryData<MenuLayoutDetail>(['menu-layout', layoutId], (old) => {
        if (!old) return old
        const newTab: MenuTab = {
          id: resp.data.child_tab_id as string,
          layout_id: old.id,
          parent_tab_id: vars.tabId,
          name: resp.data.child_tab_name ?? vars.name,
          color: null,
          display_order: 0,
          buttons: [],
        }
        return {
          ...old,
          tabs: [
            ...old.tabs.map((t) => (t.id === vars.tabId ? { ...t, buttons: [...t.buttons, resp.data] } : t)),
            newTab,
          ],
        }
      })
    },
    onError: onMutErr,
  })
  const placeButton = useMutation({
    mutationFn: ({ buttonId, tabId, gridCol, gridRow }: { buttonId: string; tabId: string; gridCol: number; gridRow: number }) =>
      api.patch<MenuButton>(`/menu-layouts/buttons/${buttonId}/place`, { tab_id: tabId, grid_col: gridCol, grid_row: gridRow }, { params }),
    onSuccess: (resp) => patchButtonMove(resp.data),
    onError: onMutErr,
  })
  const addProductButton = useMutation({
    mutationFn: ({ tabId, productRef }: { tabId: string; productRef: string; cell?: { col: number; row: number } }) =>
      api.post<MenuButton>(`/menu-layouts/${layoutId}/tabs/${tabId}/buttons`, { kind: 'product', product_ref: productRef }, { params }),
    // Append the created button straight into its tab's cached buttons array.
    // If the user clicked a specific empty cell (rather than the generic
    // "+ Product" toolbar button), create_menu_button's payload has no
    // grid_col/grid_row of its own — follow up with a /place call using the
    // id this response just returned.
    onSuccess: (resp, vars) => {
      qc.setQueryData<MenuLayoutDetail>(['menu-layout', layoutId], (old) =>
        old ? { ...old, tabs: old.tabs.map((t) => (t.id === vars.tabId ? { ...t, buttons: [...t.buttons, resp.data] } : t)) } : old,
      )
      if (vars.cell) {
        placeButton.mutate({ buttonId: resp.data.id, tabId: vars.tabId, gridCol: vars.cell.col, gridRow: vars.cell.row })
      }
    },
    onError: onMutErr,
  })
  const updateButton = useMutation({
    mutationFn: ({ tabId, buttonId, body }: { tabId: string; buttonId: string; body: Record<string, unknown> }) =>
      api.patch<MenuButton>(`/menu-layouts/${layoutId}/tabs/${tabId}/buttons/${buttonId}`, body, { params }),
    onSuccess: (resp) => patchButtonMove(resp.data),
    onError: onMutErr,
  })
  const deleteButton = useMutation({
    mutationFn: ({ tabId, buttonId }: { tabId: string; buttonId: string; childTabId?: string | null }) =>
      api.delete(`/menu-layouts/${layoutId}/tabs/${tabId}/buttons/${buttonId}`, { params }),
    // 204 No Content — nothing to read from the response, but we already
    // know everything needed (tabId/buttonId, and childTabId when deleting a
    // folder button) from the variables passed in by the caller.
    onSuccess: (_resp, vars) => {
      qc.setQueryData<MenuLayoutDetail>(['menu-layout', layoutId], (old) => {
        if (!old) return old
        const withoutButton = old.tabs.map((t) =>
          t.id === vars.tabId ? { ...t, buttons: t.buttons.filter((b) => b.id !== vars.buttonId) } : t,
        )
        const tabs = vars.childTabId ? removeTabAndDescendants(withoutButton, vars.childTabId) : withoutButton
        return { ...old, tabs }
      })
      setSelected(new Set())
    },
    onError: onMutErr,
  })
  const reorderButtons = useMutation({
    mutationFn: ({ tabId, buttonIds }: { tabId: string; buttonIds: string[] }) =>
      api.post<MenuTab>(`/menu-layouts/${layoutId}/tabs/${tabId}/buttons/reorder`, { button_ids: buttonIds }, { params }),
    // Response is the full resolved destination tab (every button it now
    // holds) — authoritative, so replace it wholesale, and drop any of those
    // button ids from every other tab's cached array (covers a cross-tab
    // drag: the button left its old tab, which this endpoint doesn't touch).
    onSuccess: (resp) => {
      const destTab = resp.data
      const movedIds = new Set(destTab.buttons.map((b) => b.id))
      qc.setQueryData<MenuLayoutDetail>(['menu-layout', layoutId], (old) => {
        if (!old) return old
        return {
          ...old,
          tabs: old.tabs.map((t) => {
            if (t.id === destTab.id) return destTab
            const filtered = t.buttons.filter((b) => !movedIds.has(b.id))
            return filtered.length === t.buttons.length ? t : { ...t, buttons: filtered }
          }),
        }
      })
    },
    onError: onMutErr,
  })
  const renameTab = useMutation({
    mutationFn: ({ tabId, name }: { tabId: string; name: string }) =>
      api.patch<MenuTab>(`/menu-layouts/${layoutId}/tabs/${tabId}`, { name }, { params }),
    // Response is the full resolved tab (route re-reads it via get_menu_layout_detail) — replace wholesale.
    onSuccess: (resp) => {
      qc.setQueryData<MenuLayoutDetail>(['menu-layout', layoutId], (old) =>
        old ? { ...old, tabs: old.tabs.map((t) => (t.id === resp.data.id ? resp.data : t)) } : old,
      )
    },
    onError: onMutErr,
  })
  const bulkRecolor = useMutation({
    mutationFn: (color: string) => api.post<MenuButton[]>(`/menu-layouts/${layoutId}/buttons/bulk-recolor`, { button_ids: [...selected], color }, { params }),
    onSuccess: (resp) => {
      const byId = new Map(resp.data.map((b) => [b.id, b]))
      qc.setQueryData<MenuLayoutDetail>(['menu-layout', layoutId], (old) =>
        old ? { ...old, tabs: old.tabs.map((t) => ({ ...t, buttons: t.buttons.map((b) => byId.get(b.id) ?? b) })) } : old,
      )
    },
    onError: onMutErr,
  })
  const bulkDelete = useMutation({
    mutationFn: () =>
      api.post<{ deleted_button_ids: string[]; deleted_tab_ids: string[] }>(
        `/menu-layouts/${layoutId}/buttons/bulk-delete`,
        { button_ids: [...selected] },
        { params },
      ),
    onSuccess: (resp) => {
      const deletedButtonIds = new Set(resp.data.deleted_button_ids)
      qc.setQueryData<MenuLayoutDetail>(['menu-layout', layoutId], (old) => {
        if (!old) return old
        let tabs = old.tabs.map((t) => ({ ...t, buttons: t.buttons.filter((b) => !deletedButtonIds.has(b.id)) }))
        for (const tabId of resp.data.deleted_tab_ids) tabs = removeTabAndDescendants(tabs, tabId)
        return { ...old, tabs }
      })
      setSelected(new Set())
    },
    onError: onMutErr,
  })
  const groupIntoTab = useMutation({
    mutationFn: (name: string) => api.post<MenuButton>(`/menu-layouts/${layoutId}/buttons/group-into-tab`, { button_ids: [...selected], name }, { params }),
    // Response is only the new folder button left behind in the source tab —
    // not a full MenuTabOut for the tab it just created. Reconstructed
    // locally: the moved buttons are exactly the ones this render's
    // `selected` ids pulled out of the source tab (group_menu_buttons_into_tab
    // only reassigns their tab_id/display_order — see service code — so the
    // rest of each button's fields carry over unchanged).
    onSuccess: (resp, groupName) => {
      const movedIds = new Set(selected)
      const newTabId = resp.data.child_tab_id as string
      qc.setQueryData<MenuLayoutDetail>(['menu-layout', layoutId], (old) => {
        if (!old) return old
        const source = currentTab ? old.tabs.find((t) => t.id === currentTab.id) : undefined
        if (!source) return old
        const movedButtons = source.buttons
          .filter((b) => movedIds.has(b.id))
          .map((b, i) => ({ ...b, tab_id: newTabId, display_order: i }))
        const newTab: MenuTab = {
          id: newTabId,
          layout_id: old.id,
          parent_tab_id: source.id,
          name: resp.data.child_tab_name ?? groupName,
          color: null,
          display_order: 0,
          buttons: movedButtons,
        }
        return {
          ...old,
          tabs: [
            ...old.tabs.map((t) =>
              t.id === source.id ? { ...t, buttons: [...t.buttons.filter((b) => !movedIds.has(b.id)), resp.data] } : t,
            ),
            newTab,
          ],
        }
      })
      setSelected(new Set())
    },
    onError: onMutErr,
  })
  const publish = useMutation({
    mutationFn: () => api.post<PublishResult>(`/menu-layouts/${layoutId}/publish`, {}, { params }),
    // PublishResult carries a MenuLayoutOut (layout-level fields only, no
    // tabs) — merge those fields over the cached detail, keep tabs as-is.
    onSuccess: (resp) => {
      qc.setQueryData<MenuLayoutDetail>(['menu-layout', layoutId], (old) => (old ? { ...old, ...resp.data.layout } : old))
      setWarnings(resp.data.warnings)
    },
    onError: onMutErr,
  })
  const unpublish = useMutation({
    mutationFn: () => api.post<MenuLayout>(`/menu-layouts/${layoutId}/unpublish`, {}, { params }),
    onSuccess: (resp) => {
      qc.setQueryData<MenuLayoutDetail>(['menu-layout', layoutId], (old) => (old ? { ...old, ...resp.data } : old))
    },
    onError: onMutErr,
  })

  if (isLoading || !layout) {
    return <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
  }

  const moveSelectionToTab = (targetTabId: string) => {
    const targetTab = tabsById.get(targetTabId)
    if (!targetTab || !currentTab) return
    // Refuse moving a folder button into its own nested tab.
    const movingIds = [...selected]
    const invalid = movingIds.some((id) => {
      const btn = currentTab.buttons.find((b) => b.id === id)
      return btn?.kind === 'folder' && btn.child_tab_id === targetTabId
    })
    if (invalid || targetTabId === effectiveTabId) return
    const existing = targetTab.buttons.map((b) => b.id).filter((id) => !selected.has(id))
    reorderButtons.mutate({ tabId: targetTabId, buttonIds: [...existing, ...movingIds] })
    setSelected(new Set())
    setMoveMenuOpen(false)
  }

  const moveTargets = [
    ...(currentTab?.buttons.filter((b) => b.kind === 'folder' && b.child_tab_id && !selected.has(b.id)) ?? []).map((b) => ({
      id: b.child_tab_id as string,
      label: `↳ ${b.child_tab_name ?? 'Tab'}`,
    })),
    ...topLevelTabs.filter((t) => t.id !== effectiveTabId).map((t) => ({ id: t.id, label: `Tab · ${t.name}` })),
  ]

  const handlePointerDownTile = (e: React.PointerEvent, buttonId: string) => {
    if (e.button !== 0) return
    e.preventDefault()
    const startX = e.clientX
    const startY = e.clientY
    const additive = e.shiftKey || e.metaKey || e.ctrlKey
    let moved = false

    const onMove = (ev: PointerEvent) => {
      if (!moved && Math.hypot(ev.clientX - startX, ev.clientY - startY) > 5) {
        moved = true
        setSelected((prev) => (prev.has(buttonId) ? prev : new Set([buttonId])))
        setDragging(true)
      }
      if (moved) {
        const el = document.elementFromPoint(ev.clientX, ev.clientY)
        const dropEl = el?.closest('[data-drop]') ?? null
        const tileEl = el?.closest('[data-tile-idx]') ?? null
        let target = parseDropAttr(dropEl?.getAttribute('data-drop') ?? null)
        let insertion: number | null = null
        if (tileEl) {
          // Over a grid tile: the outer 25% edges mean "insert beside it";
          // a folder tile's middle 50% still means "drop into the folder".
          // A non-folder tile is an insertion target across its whole width,
          // so a product can be repositioned next to a folder without
          // falling into it (the reported swap-into-group problem).
          const idx = Number(tileEl.getAttribute('data-tile-idx'))
          const rect = tileEl.getBoundingClientRect()
          const relX = (ev.clientX - rect.left) / rect.width
          const isFolderTile = tileEl.hasAttribute('data-drop')
          if (!isFolderTile || relX < 0.25 || relX > 0.75) {
            insertion = relX < 0.5 ? idx : idx + 1
            target = null
          }
        }
        setDragPos({ x: ev.clientX, y: ev.clientY })
        setDragOverTarget(target)
        setDropIndex(insertion)
      }
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      if (!moved) {
        const prev = selectedRef.current
        if (additive) {
          const next = new Set(prev)
          if (next.has(buttonId)) next.delete(buttonId)
          else next.add(buttonId)
          setSelected(next)
        } else {
          setSelected(prev.size === 1 && prev.has(buttonId) ? new Set() : new Set([buttonId]))
        }
      } else {
        setDragging(false)
        const target = dragOverTargetRef.current
        const insertion = dropIndexRef.current
        setDragOverTarget(null)
        setDropIndex(null)
        if (insertion !== null) reorderSelectionWithinTab(insertion, selectedRef.current)
        else if (target?.kind === 'cell') placeSelectionAtCell(target, selectedRef.current)
        else if (target?.kind === 'tab') moveSelectionToTabWithIds(target.tabId, selectedRef.current)
      }
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  // Reposition the dragged selection within the current tab at the given
  // insertion index (a boundary in the pre-drag button order).
  const reorderSelectionWithinTab = (insertion: number, ids: Set<string>) => {
    if (!currentTab) return
    const order = currentTab.buttons.map((b) => b.id)
    // The insertion boundary shifts left by however many dragged buttons sat
    // before it — remove them first, then splice the dragged block back in.
    const draggedBefore = order.slice(0, insertion).filter((id) => ids.has(id)).length
    const remaining = order.filter((id) => !ids.has(id))
    const draggedInOrder = order.filter((id) => ids.has(id))
    remaining.splice(insertion - draggedBefore, 0, ...draggedInOrder)
    // No-op drop (same position) — skip the round trip.
    if (remaining.every((id, i) => id === order[i])) return
    reorderButtons.mutate({ tabId: currentTab.id, buttonIds: remaining })
  }

  // Same move logic as moveSelectionToTab, but takes an explicit id set —
  // used by the pointer-drag handler, which reads selectedRef.current
  // directly (see its declaration) rather than the possibly-stale `selected`
  // captured when this tile's onPointerDown closure was created.
  const moveSelectionToTabWithIds = (targetTabId: string, ids: Set<string>) => {
    const targetTab = tabsById.get(targetTabId)
    if (!targetTab || !currentTab || targetTabId === effectiveTabId) return
    const movingIds = [...ids]
    const invalid = movingIds.some((id) => {
      const btn = currentTab.buttons.find((b) => b.id === id)
      return btn?.kind === 'folder' && btn.child_tab_id === targetTabId
    })
    if (invalid) return
    const existing = targetTab.buttons.map((b) => b.id).filter((id) => !ids.has(id))
    reorderButtons.mutate({ tabId: targetTabId, buttonIds: [...existing, ...movingIds] })
    setSelected(new Set())
  }

  // Drop onto an empty dashed "+" cell — places the dragged button at that
  // exact grid_col/grid_row via PATCH .../place. A single explicit cell only
  // makes sense for one button at a time; a multi-selection drag falls back
  // to the existing "move into this tab, appended at the end" behavior
  // (same as dropping the selection on the tab itself).
  const placeSelectionAtCell = (target: { tabId: string; gridCol: number; gridRow: number }, ids: Set<string>) => {
    if (ids.size === 1) {
      const buttonId = [...ids][0]
      placeButton.mutate({ buttonId, tabId: target.tabId, gridCol: target.gridCol, gridRow: target.gridRow })
      setSelected(new Set())
    } else {
      moveSelectionToTabWithIds(target.tabId, ids)
    }
  }

  const handleResizeStart = (e: React.PointerEvent, button: MenuButton) => {
    e.stopPropagation()
    e.preventDefault()
    const grid = gridRef.current
    if (!grid || !currentTab) return
    const rect = grid.getBoundingClientRect()
    const cols = 6
    const gap = 10
    const rowH = 92
    const cellW = (rect.width - gap * (cols - 1)) / cols
    const startW = button.width
    const startH = button.height
    const sx = e.clientX
    const sy = e.clientY
    let w = startW
    let h = startH
    const onMove = (ev: PointerEvent) => {
      const dw = Math.round((ev.clientX - sx) / (cellW + gap))
      const dh = Math.round((ev.clientY - sy) / (rowH + gap))
      w = Math.min(6, Math.max(1, startW + dw))
      h = Math.min(4, Math.max(1, startH + dh))
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      if (w !== startW || h !== startH) {
        updateButton.mutate({ tabId: currentTab.id, buttonId: button.id, body: { width: w, height: h } })
      }
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  const selectedButtons = currentTab ? currentTab.buttons.filter((b) => selected.has(b.id)) : []
  const oneSelected = selectedButtons.length === 1 ? selectedButtons[0] : null

  return (
    <div className="space-y-3" onClick={() => setMoveMenuOpen(false)}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button onClick={onBack} className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100">
          ‹ Layouts
        </button>
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-sm" style={{ background: layout.color }} />
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">{layout.name}</h2>
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
              layout.is_published ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
            }`}
          >
            {layout.is_published ? 'Published' : 'Unpublished'}
          </span>
          <span className="text-xs text-gray-400 dark:text-gray-500">v{layout.version}</span>
          <button onClick={() => setShowHours(true)} className="px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-semibold text-gray-600 dark:text-gray-300 rounded-md">
            ◷ {activeTimeLabel(layout)}
          </button>
          <button
            onClick={() => (layout.is_published ? unpublish.mutate() : publish.mutate())}
            className="bg-brand-600 hover:bg-brand-700 text-white text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
          >
            {layout.is_published ? 'Unpublish' : 'Publish'}
          </button>
        </div>
      </div>

      {actionError && (
        <p className="text-sm text-red-600 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">
          {actionError}
        </p>
      )}

      {warnings && (
        <div className={`rounded-lg border px-3 py-2 text-xs ${warnings.length ? 'bg-amber-50 border-amber-200 text-amber-800' : 'bg-green-50 border-green-200 text-green-700'}`}>
          {warnings.length === 0 ? (
            'Published with no warnings.'
          ) : (
            <>
              <p className="font-medium mb-1">Published, but {warnings.length} button(s) need attention:</p>
              <ul className="list-disc list-inside space-y-0.5">
                {warnings.map((w) => (
                  <li key={w.button_id}>
                    {w.tab_name}: {w.product_ref} — {w.reason === 'product_not_found' ? 'product not found' : 'product is inactive'}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      <div className="flex border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden" style={{ minHeight: 520 }}>
        {/* Rail */}
        <div className="w-48 shrink-0 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 p-3 flex flex-col gap-1 overflow-auto">
          <div className="text-[10.5px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 px-1 pb-1">Tabs</div>
          {topLevelTabs.map((tab) => (
            <div
              key={tab.id}
              data-drop={`tab:${tab.id}`}
              onClick={() => { setCurrentTabId(tab.id); setSelected(new Set()) }}
              className={`flex items-center gap-2 px-2.5 py-2 rounded-lg text-sm cursor-pointer ${
                tab.id === effectiveTabId ? 'bg-brand-50 dark:bg-brand-950/40 text-brand-800 dark:text-brand-300 font-medium' : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
              } ${dragOverTarget?.kind === 'tab' && dragOverTarget.tabId === tab.id ? 'ring-2 ring-brand-500' : ''}`}
            >
              <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: tab.color ?? '#5A5550' }} />
              <span className="truncate flex-1">{tab.name}</span>
              <span className="text-[11px] text-gray-400 dark:text-gray-500">{tab.buttons.length}</span>
            </div>
          ))}
          <button
            onClick={() => { const name = prompt('New tab name'); if (name) addTab.mutate(name) }}
            className="mt-1 text-xs px-2.5 py-2 border border-dashed border-gray-300 dark:border-gray-600 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 text-center"
          >
            + Add tab
          </button>
          <div className="flex-1" />
          <p className="text-[11px] text-gray-400 dark:text-gray-500 px-1 leading-relaxed">
            Click a button to select. Shift-click adds more. Drag onto a tab or folder to move.
          </p>
        </div>

        {/* Grid */}
        <div className="flex-1 min-w-0 flex flex-col">
          <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center gap-2 text-sm font-semibold min-w-0 flex-wrap">
              {breadcrumb.map((tab, i) => (
                <span key={tab.id} className="flex items-center gap-2">
                  {i > 0 && <span className="text-gray-300 dark:text-gray-600">›</span>}
                  <button
                    onClick={() => { setCurrentTabId(tab.id); setSelected(new Set()) }}
                    className={i === breadcrumb.length - 1 ? 'text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400 hover:text-brand-600'}
                  >
                    {tab.name}
                  </button>
                </span>
              ))}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={() => { const name = prompt('New tab (folder) name'); if (name && currentTab) addFolderButton.mutate({ tabId: currentTab.id, name }) }}
                className="text-xs px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                + Tab
              </button>
              <button
                onClick={() => setShowProductPicker(true)}
                className="text-xs px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                + Product
              </button>
              <button
                onClick={() => { if (effectiveTabId) setExtraRowsByTab((prev) => ({ ...prev, [effectiveTabId]: (prev[effectiveTabId] ?? 0) + 1 })) }}
                className="text-xs px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                + Row
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-auto p-4 relative">
            {!currentTab ? (
              <p className="text-sm text-gray-400 dark:text-gray-500">Add a tab to start placing buttons.</p>
            ) : (
              <div
                ref={gridRef}
                className="grid gap-2.5"
                style={{ gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gridAutoRows: 92, gridAutoFlow: 'row dense' }}
              >
                {currentTab.buttons.map((button, tileIdx) => {
                  const isFolder = button.kind === 'folder'
                  const base = button.color ?? (isFolder ? '#5A5550' : button.category_color ?? '#5A5550')
                  const isSel = selected.has(button.id)
                  return (
                    <div
                      key={button.id}
                      data-tile-idx={tileIdx}
                      data-drop={isFolder && button.child_tab_id ? `tab:${button.child_tab_id}` : undefined}
                      onPointerDown={(e) => handlePointerDownTile(e, button.id)}
                      onClick={(e) => e.stopPropagation()}
                      className={`relative rounded-xl px-3 py-2.5 flex flex-col justify-between cursor-pointer select-none shadow-sm touch-none ${
                        isSel ? 'ring-[3px] ring-brand-600' : ''
                      } ${isFolder && dragOverTarget?.kind === 'tab' && dragOverTarget.tabId === button.child_tab_id ? 'ring-2 ring-brand-400' : ''}`}
                      style={{
                        // grid_col/grid_row (drag-to-any-cell placement) pin the
                        // tile to an explicit cell; null falls back to dense
                        // auto-flow packing via display_order, same as before.
                        gridColumn: button.grid_col !== null ? `${button.grid_col + 1} / span ${button.width}` : `span ${button.width}`,
                        gridRow: button.grid_row !== null ? `${button.grid_row + 1} / span ${button.height}` : `span ${button.height}`,
                        background: isFolder ? undefined : base,
                        color: isFolder ? undefined : textColorOn(base),
                      }}
                    >
                      {/* Insertion bar: dropping here repositions the dragged button(s) beside this tile */}
                      {dropIndex === tileIdx && (
                        <div className="absolute -left-[7px] top-1 bottom-1 w-[4px] rounded-full bg-brand-600 pointer-events-none" />
                      )}
                      {dropIndex === tileIdx + 1 && tileIdx === currentTab.buttons.length - 1 && (
                        <div className="absolute -right-[7px] top-1 bottom-1 w-[4px] rounded-full bg-brand-600 pointer-events-none" />
                      )}
                      {isFolder && <div className="h-1.5 rounded-sm w-8 mb-1" style={{ background: button.color ?? '#A82040' }} />}
                      <div className={`font-semibold text-[13.5px] leading-tight overflow-hidden ${isFolder ? 'text-gray-900 dark:text-gray-100' : ''}`}>
                        {isFolder ? button.child_tab_name : button.product_name ?? button.product_ref}
                      </div>
                      <div className="flex items-end justify-between gap-1.5">
                        <span className={`font-mono text-[11.5px] ${isFolder ? 'text-gray-500 dark:text-gray-400' : 'opacity-90'}`}>
                          {isFolder ? '' : button.price_cents !== null ? centsToDisplay(button.price_cents) : ''}
                        </span>
                        {isFolder && <span className="text-[10px] font-medium opacity-70 text-gray-500 dark:text-gray-400">{button.child_tab_button_count ?? 0} items</span>}
                      </div>
                      {isSel && <div className="absolute top-1.5 right-1.5 w-[19px] h-[19px] rounded-full bg-brand-600 text-white text-[11px] flex items-center justify-center shadow">✓</div>}
                      {isFolder && (
                        <button
                          onPointerDown={(e) => e.stopPropagation()}
                          onClick={(e) => { e.stopPropagation(); if (button.child_tab_id) { setCurrentTabId(button.child_tab_id); setSelected(new Set()) } }}
                          className="absolute top-1.5 right-1.5 w-[23px] h-[23px] rounded-md bg-black/10 hover:bg-brand-600 hover:text-white flex items-center justify-center text-[12px] text-gray-600"
                          title="Open tab"
                        >
                          ⤢
                        </button>
                      )}
                      {isSel && (
                        <div
                          onPointerDown={(e) => handleResizeStart(e, button)}
                          className="absolute bottom-0.5 right-0.5 w-4 h-4 cursor-nwse-resize flex items-end justify-end opacity-70 text-[12px]"
                        >
                          ⟌
                        </div>
                      )}
                    </div>
                  )
                })}
                {(() => {
                  // Pad the grid with dashed "+" slots to full rows of 6:
                  // an empty tab shows one full row, and "+ Row" adds 6 more.
                  // Cells are approximated as width×height per button — with
                  // grid-auto-flow:dense the browser packs around spans, so
                  // this is the same arithmetic the packing works out to
                  // whenever tiles tessellate cleanly. Each empty slot's own
                  // grid_col/grid_row (for drag/click placement) is derived
                  // from the same running cell offset — accurate whenever
                  // tiles tessellate cleanly, same caveat as the count above;
                  // an explicitly-placed button sitting at a discontinuous
                  // cell can make an empty tile's computed coordinate overlap
                  // it visually, which this approximation doesn't detect.
                  const cellsUsed = currentTab.buttons.reduce((sum, b) => sum + b.width * b.height, 0)
                  const rows = Math.max(1, Math.ceil(cellsUsed / 6)) + (extraRowsByTab[currentTab.id] ?? 0)
                  const emptyCount = Math.max(0, rows * 6 - cellsUsed)
                  return Array.from({ length: emptyCount }, (_, i) => {
                    const offset = cellsUsed + i
                    const col = offset % 6
                    const row = Math.floor(offset / 6)
                    const isDragOver =
                      dragOverTarget?.kind === 'cell' &&
                      dragOverTarget.tabId === currentTab.id &&
                      dragOverTarget.gridCol === col &&
                      dragOverTarget.gridRow === row
                    return (
                      <button
                        key={`empty-${i}`}
                        data-drop={`cell:${currentTab.id}:${col}:${row}`}
                        onClick={() => { setPendingCell({ col, row }); setShowProductPicker(true) }}
                        className={`border-[1.5px] border-dashed rounded-xl flex items-center justify-center text-2xl ${
                          isDragOver
                            ? 'border-brand-500 ring-2 ring-brand-400 text-brand-500'
                            : 'border-gray-300 dark:border-gray-600 text-gray-300 dark:text-gray-600 hover:border-brand-500 hover:text-brand-600'
                        }`}
                        style={{ gridColumn: 'span 1', gridRow: 'span 1' }}
                      >
                        +
                      </button>
                    )
                  })
                })()}
              </div>
            )}

            {dragging && (
              <div className="fixed z-[120] pointer-events-none bg-gray-900 text-white px-3.5 py-2 rounded-lg text-xs font-semibold shadow-xl" style={{ left: dragPos.x + 16, top: dragPos.y + 14 }}>
                Moving {selected.size} button{selected.size === 1 ? '' : 's'}
              </div>
            )}

            {selected.size >= 2 && (
              <div className="sticky bottom-3 mx-auto mt-3 max-w-[720px] flex items-center gap-3.5 bg-gray-900 text-white rounded-xl px-4 py-3 shadow-xl" onClick={(e) => e.stopPropagation()}>
                <span className="text-sm font-semibold">{selected.size} selected</span>
                <div className="flex items-center gap-1.5">
                  {MENU_STUDIO_PALETTE.map((c) => (
                    <button key={c} onClick={() => bulkRecolor.mutate(c)} className="w-6 h-6 rounded-md" style={{ background: c }} />
                  ))}
                  <label className="w-6 h-6 rounded-md relative overflow-hidden cursor-pointer" style={{ background: 'conic-gradient(from 0deg,#e74c3c,#f1c40f,#2ecc71,#3498db,#9b59b6,#e74c3c)' }}>
                    <input type="color" onChange={(e) => bulkRecolor.mutate(e.target.value)} className="absolute inset-0 opacity-0 cursor-pointer" />
                  </label>
                </div>
                <div className="w-px h-5 bg-white/20" />
                <div className="relative">
                  <button onClick={(e) => { e.stopPropagation(); setMoveMenuOpen((o) => !o) }} className="text-xs font-semibold px-2.5 py-1.5 rounded-md bg-white/10 hover:bg-white/20">
                    Move to ▾
                  </button>
                  {moveMenuOpen && (
                    <div className="absolute bottom-full mb-2 left-0 min-w-[210px] bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-1" onClick={(e) => e.stopPropagation()}>
                      <div className="px-3 py-1.5 text-[10.5px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Move into tab</div>
                      {moveTargets.map((t) => (
                        <button key={t.id} onClick={() => moveSelectionToTab(t.id)} className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100 dark:hover:bg-gray-700">
                          {t.label}
                        </button>
                      ))}
                      {moveTargets.length === 0 && <div className="px-3 py-1.5 text-xs text-gray-400">No other tabs yet.</div>}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => { const name = prompt('New tab name'); if (name) groupIntoTab.mutate(name) }}
                  className="text-xs font-semibold px-2.5 py-1.5 rounded-md bg-white/10 hover:bg-white/20"
                >
                  Group into tab
                </button>
                <button onClick={() => bulkDelete.mutate()} className="text-xs font-semibold px-2.5 py-1.5 rounded-md border border-white/30">
                  Delete
                </button>
                <span onClick={() => setSelected(new Set())} className="ml-auto text-xs text-white/60 hover:text-white cursor-pointer">
                  Clear
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Inspector */}
        {oneSelected && currentTab && (
          <Inspector
            button={oneSelected}
            products={products}
            onLinkProduct={(ref) => updateButton.mutate({ tabId: currentTab.id, buttonId: oneSelected.id, body: { product_ref: ref } })}
            onRename={(name) => renameTab.mutate({ tabId: oneSelected.child_tab_id as string, name })}
            onOpenTab={() => { if (oneSelected.child_tab_id) { setCurrentTabId(oneSelected.child_tab_id); setSelected(new Set()) } }}
            onColor={(color) => updateButton.mutate({ tabId: currentTab.id, buttonId: oneSelected.id, body: { color } })}
            onUseCategoryDefault={() => updateButton.mutate({ tabId: currentTab.id, buttonId: oneSelected.id, body: { color: null } })}
            onResize={(width, height) => updateButton.mutate({ tabId: currentTab.id, buttonId: oneSelected.id, body: { width, height } })}
            onDelete={() =>
              deleteButton.mutate({
                tabId: currentTab.id,
                buttonId: oneSelected.id,
                childTabId: oneSelected.kind === 'folder' ? oneSelected.child_tab_id : null,
              })
            }
          />
        )}
      </div>

      {showHours && (
        <ActiveHoursModal brandId={brandId} layout={layout} onClose={() => setShowHours(false)} onSaved={() => { invalidate(); setShowHours(false) }} />
      )}
      {showProductPicker && currentTab && (
        <ProductPickerModal
          products={products}
          onClose={() => { setShowProductPicker(false); setPendingCell(null) }}
          onPick={(ref) => {
            addProductButton.mutate({ tabId: currentTab.id, productRef: ref, cell: pendingCell ?? undefined })
            setShowProductPicker(false)
            setPendingCell(null)
          }}
        />
      )}
    </div>
  )
}

function Inspector({
  button,
  products,
  onLinkProduct,
  onRename,
  onOpenTab,
  onColor,
  onUseCategoryDefault,
  onResize,
  onDelete,
}: {
  button: MenuButton
  products: ProductListItem[]
  onLinkProduct: (ref: string) => void
  onRename: (name: string) => void
  onOpenTab: () => void
  onColor: (color: string) => void
  onUseCategoryDefault: () => void
  onResize: (width: number, height: number) => void
  onDelete: () => void
}) {
  const isFolder = button.kind === 'folder'
  const base = button.color ?? (isFolder ? '#5A5550' : button.category_color ?? '#5A5550')

  return (
    <div className="w-72 shrink-0 bg-white dark:bg-gray-800 border-l border-gray-200 dark:border-gray-700 p-4 overflow-auto flex flex-col gap-4">
      <div>
        <div className="text-[10.5px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Preview</div>
        <div
          className="rounded-xl px-3 py-2.5 flex flex-col justify-between"
          style={{ height: 74, background: isFolder ? undefined : base, color: isFolder ? undefined : textColorOn(base) }}
        >
          {isFolder && <div className="h-1.5 rounded-sm w-8" style={{ background: button.color ?? '#A82040' }} />}
          <div className="font-semibold text-[13.5px]">{isFolder ? button.child_tab_name : button.product_name ?? button.product_ref}</div>
          {!isFolder && button.price_cents !== null && <span className="font-mono text-[11.5px]">{centsToDisplay(button.price_cents)}</span>}
        </div>
      </div>

      {!isFolder && (
        <div>
          <div className="text-[10.5px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-1.5">Linked product</div>
          <select
            value={button.product_ref ?? ''}
            onChange={(e) => onLinkProduct(e.target.value)}
            className="w-full px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded-lg text-sm"
          >
            <option value="">Choose product…</option>
            {products.filter((p) => p.is_active).map((p) => (
              <option key={p.id} value={p.ref}>{p.name}</option>
            ))}
          </select>
        </div>
      )}

      {isFolder && (
        <div>
          <div className="text-[10.5px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-1.5">Tab name</div>
          <input
            defaultValue={button.child_tab_name ?? ''}
            onBlur={(e) => { if (e.target.value && e.target.value !== button.child_tab_name) onRename(e.target.value) }}
            className="w-full px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded-lg text-sm"
          />
          <button onClick={onOpenTab} className="mt-2.5 w-full text-xs font-semibold px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md text-gray-600 dark:text-gray-300">
            Open tab ⤢
          </button>
        </div>
      )}

      <div>
        <div className="text-[10.5px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Colour</div>
        <div className="flex flex-wrap gap-2">
          {MENU_STUDIO_PALETTE.map((c) => (
            <button
              key={c}
              onClick={() => onColor(c)}
              className={`w-7 h-7 rounded-lg border-2 ${button.color === c ? 'border-gray-900 dark:border-gray-100' : 'border-transparent'}`}
              style={{ background: c }}
            />
          ))}
        </div>
        <div className="flex items-center gap-3.5 mt-3">
          <label className="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400 cursor-pointer">
            <input type="color" value={base} onChange={(e) => onColor(e.target.value)} className="w-[30px] h-[30px] border-none bg-transparent cursor-pointer p-0" />
            Custom
          </label>
          {!isFolder && (
            <button onClick={onUseCategoryDefault} className="text-xs font-semibold text-brand-600 dark:text-brand-400">
              Category default
            </button>
          )}
        </div>
      </div>

      <div>
        <div className="text-[10.5px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Size (grid cells)</div>
        <div className="flex gap-3">
          <div className="flex-1">
            <div className="text-[11px] text-gray-400 dark:text-gray-500 mb-1">Width</div>
            <div className="flex items-center justify-between border border-gray-300 dark:border-gray-600 rounded-lg px-2 py-1">
              <button onClick={() => onResize(Math.max(1, button.width - 1), button.height)} className="text-gray-500 dark:text-gray-400 px-1">−</button>
              <span className="text-sm font-medium">{button.width}</span>
              <button onClick={() => onResize(Math.min(6, button.width + 1), button.height)} className="text-gray-500 dark:text-gray-400 px-1">+</button>
            </div>
          </div>
          <div className="flex-1">
            <div className="text-[11px] text-gray-400 dark:text-gray-500 mb-1">Height</div>
            <div className="flex items-center justify-between border border-gray-300 dark:border-gray-600 rounded-lg px-2 py-1">
              <button onClick={() => onResize(button.width, Math.max(1, button.height - 1))} className="text-gray-500 dark:text-gray-400 px-1">−</button>
              <span className="text-sm font-medium">{button.height}</span>
              <button onClick={() => onResize(button.width, Math.min(4, button.height + 1))} className="text-gray-500 dark:text-gray-400 px-1">+</button>
            </div>
          </div>
        </div>
        <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-2">Or drag the ⟌ corner of a selected button on the grid.</p>
      </div>

      <div className="flex-1" />
      <button onClick={onDelete} className="w-full text-center text-xs font-semibold px-2.5 py-1.5 rounded-md border border-brand-300 dark:border-brand-700 text-brand-600 dark:text-brand-400">
        Delete button
      </button>
    </div>
  )
}

function ProductPickerModal({
  products,
  onClose,
  onPick,
}: {
  products: ProductListItem[]
  onClose: () => void
  onPick: (ref: string) => void
}) {
  const [search, setSearch] = useState('')
  const matches = products.filter(
    (p) => p.is_active && (p.name.toLowerCase().includes(search.toLowerCase()) || p.ref.toLowerCase().includes(search.toLowerCase()))
  )

  return (
    <Modal title="Add product button" onClose={onClose}>
      <div className="space-y-3">
        <input
          autoFocus
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search products…"
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <div className="max-h-72 overflow-y-auto divide-y divide-gray-100 dark:divide-gray-800">
          {matches.slice(0, 50).map((p) => (
            <button
              key={p.id}
              onClick={() => onPick(p.ref)}
              className="w-full flex items-center justify-between gap-2 text-left text-sm px-2 py-2 hover:bg-gray-50 dark:hover:bg-gray-800"
            >
              <span className="flex items-center gap-2 min-w-0">
                <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: p.category_color }} />
                <span className="truncate text-gray-900 dark:text-gray-100">{p.name}</span>
              </span>
              <span className="text-xs text-gray-400 dark:text-gray-500 font-mono shrink-0">{centsToDisplay(p.base_price_cents)}</span>
            </button>
          ))}
          {matches.length === 0 && <p className="text-sm text-gray-400 dark:text-gray-500 px-2 py-4 text-center">No matching products.</p>}
        </div>
      </div>
    </Modal>
  )
}
