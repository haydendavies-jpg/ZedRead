/** Modifiers (option sets) management page — cards with comboing (linked groups).
 *
 * Menu Studio redesign: one card per modifier group, options listed with a
 * "linked groups" chip that expands an inline nested cascade showing each
 * linked group's own options (design_handoff_menu_studio/README.md
 * "Modifiers tab (option sets)" + Modifier Comboing Options.dc.html —
 * "option 1", the inline-nested-cascade approach).
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { apiErrorMessage } from '../../utils/apiError'
import { centsToDisplay } from '../../utils/menuStudio'
import type { ModifierGroupDetail } from '../../types'

export function ModifiersPage() {
  const qc = useQueryClient()
  const brandId = useMgmtBrandId()
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [formError, setFormError] = useState<string | null>(null)

  const params = brandId ? { brand_id: brandId } : {}

  const { data: groups = [], isLoading } = useQuery<ModifierGroupDetail[]>({
    queryKey: ['modifier-groups-detailed', brandId],
    queryFn: () => api.get('/modifier-groups/detailed', { params: { ...params, limit: 200 } }).then((r) => r.data),
    enabled: !!brandId,
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['modifier-groups-detailed', brandId] })

  const showError = (e: unknown, fallback: string) => setFormError(apiErrorMessage(e, fallback))

  const createGroup = useMutation({
    mutationFn: () => api.post('/modifier-groups', { name: 'New modifier', min_selections: 0, max_selections: 1 }, { params }),
    onSuccess: invalidate,
    onError: (e: unknown) => showError(e, 'Failed to create modifier.'),
  })

  const duplicateGroup = useMutation({
    mutationFn: (groupId: string) => api.post(`/modifier-groups/${groupId}/duplicate`, {}, { params }),
    onSuccess: invalidate,
    onError: (e: unknown) => showError(e, 'Failed to duplicate modifier.'),
  })

  const deleteGroup = useMutation({
    mutationFn: (groupId: string) => api.delete(`/modifier-groups/${groupId}`, { params }),
    onSuccess: invalidate,
    onError: (e: unknown) => showError(e, 'Failed to delete modifier.'),
  })

  const patchGroup = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => api.patch(`/modifier-groups/${id}`, body, { params }),
    onSuccess: invalidate,
    onError: (e: unknown) => showError(e, 'Failed to update modifier.'),
  })

  const createOption = useMutation({
    mutationFn: (groupId: string) => api.post(`/modifier-groups/${groupId}/options`, { name: 'New option', price_delta_cents: 0 }, { params }),
    onSuccess: invalidate,
    onError: (e: unknown) => showError(e, 'Failed to add option.'),
  })

  const patchOption = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => api.patch(`/modifier-options/${id}`, body, { params }),
    onSuccess: invalidate,
    onError: (e: unknown) => showError(e, 'Failed to update option.'),
  })

  const deleteOption = useMutation({
    mutationFn: (optionId: string) => api.delete(`/modifier-options/${optionId}`, { params }),
    onSuccess: invalidate,
    onError: (e: unknown) => showError(e, 'Failed to delete option.'),
  })

  const linkGroup = useMutation({
    mutationFn: ({ optionId, linkedGroupId }: { optionId: string; linkedGroupId: string }) =>
      api.post(`/modifier-options/${optionId}/links`, { linked_group_id: linkedGroupId }, { params }),
    onSuccess: invalidate,
    onError: (e: unknown) => showError(e, 'Failed to link modifier group.'),
  })

  const unlinkGroup = useMutation({
    mutationFn: ({ optionId, linkedGroupId }: { optionId: string; linkedGroupId: string }) =>
      api.delete(`/modifier-options/${optionId}/links/${linkedGroupId}`, { params }),
    onSuccess: invalidate,
    onError: (e: unknown) => showError(e, 'Failed to unlink modifier group.'),
  })

  const toggleExpanded = (optionId: string) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(optionId)) next.delete(optionId)
      else next.add(optionId)
      return next
    })

  if (!brandId) {
    return <div className="flex items-center justify-center h-64 text-sm text-gray-400">No brand context available.</div>
  }

  return (
    <div className="p-4 sm:p-6" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Modifiers</h1>
      </div>
      {formError && (
        <p className="text-sm text-red-600 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2 mb-4">
          {formError}
        </p>
      )}
      {isLoading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {groups.map((g) => (
            <div key={g.id} className="flex flex-col bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
              <div className="px-4 pt-4 pb-1">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="font-serif font-semibold text-base text-gray-900 dark:text-gray-100">{g.name}</h2>
                  <div className="flex items-center gap-2.5 text-gray-300 dark:text-gray-600 shrink-0">
                    <button title="Duplicate" onClick={() => duplicateGroup.mutate(g.id)} className="hover:text-gray-600 dark:hover:text-gray-300">⧉</button>
                    <button title="Delete" onClick={() => { if (confirm(`Delete "${g.name}"?`)) deleteGroup.mutate(g.id) }} className="hover:text-red-500">✕</button>
                  </div>
                </div>
                <div className="flex items-center gap-4 mt-3 mb-1.5">
                  <label className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={g.min_selections > 0}
                      onChange={(e) => patchGroup.mutate({ id: g.id, body: { min_selections: e.target.checked ? 1 : 0 } })}
                      className="rounded border-gray-300 dark:border-gray-600 text-brand-600 focus:ring-brand-500"
                    />
                    Required
                  </label>
                  <label className="flex items-center gap-1.5 text-xs text-gray-400 dark:text-gray-500">
                    Min
                    <BufferedInput
                      type="number"
                      min={0}
                      value={String(g.min_selections)}
                      onCommit={(v) => { const n = Number(v); if (!Number.isNaN(n)) patchGroup.mutate({ id: g.id, body: { min_selections: n } }) }}
                      className="w-11 text-center border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded font-mono text-xs py-0.5"
                    />
                  </label>
                  <label className="flex items-center gap-1.5 text-xs text-gray-400 dark:text-gray-500">
                    Max
                    <BufferedInput
                      type="number"
                      min={1}
                      value={String(g.max_selections)}
                      onCommit={(v) => { const n = Number(v); if (!Number.isNaN(n)) patchGroup.mutate({ id: g.id, body: { max_selections: n } }) }}
                      className="w-11 text-center border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded font-mono text-xs py-0.5"
                    />
                  </label>
                </div>
              </div>

              <div className="flex-1 px-4 pt-1 pb-3 border-t border-gray-100 dark:border-gray-700 mt-1.5">
                {g.options.map((o) => (
                  <div key={o.id}>
                    <div className="flex items-center gap-2.5 py-1.5">
                      <span className="text-gray-300 dark:text-gray-600 text-xs tracking-tighter">⠿</span>
                      <BufferedInput
                        value={o.name}
                        onCommit={(v) => { if (v.trim()) patchOption.mutate({ id: o.id, body: { name: v } }) }}
                        className="flex-1 min-w-0 text-sm text-gray-900 dark:text-gray-100 bg-transparent focus:outline-none focus:bg-gray-50 dark:focus:bg-gray-700 rounded px-1 -mx-1"
                      />
                      {o.linked_groups.length > 0 && (
                        <button
                          onClick={() => toggleExpanded(o.id)}
                          className="flex items-center gap-1 bg-brand-100 dark:bg-brand-950/50 text-brand-700 dark:text-brand-300 rounded-full px-2 py-0.5 text-[10.5px] font-semibold whitespace-nowrap"
                        >
                          🔗 {o.linked_groups.length} <span className="text-[9px]">{expanded.has(o.id) ? '︿' : '⌄'}</span>
                        </button>
                      )}
                      <span className="text-xs font-medium text-gray-400 dark:text-gray-500">+$</span>
                      <BufferedInput
                        type="number"
                        step="0.01"
                        value={(o.price_delta_cents / 100).toFixed(2)}
                        onCommit={(v) => {
                          const cents = Math.round(Number(v) * 100)
                          if (!Number.isNaN(cents)) patchOption.mutate({ id: o.id, body: { price_delta_cents: cents } })
                        }}
                        className="w-14 text-right border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded font-mono text-xs py-0.5 px-1"
                      />
                      <button onClick={() => deleteOption.mutate(o.id)} className="text-gray-300 dark:text-gray-600 hover:text-red-500 text-xs">✕</button>
                    </div>

                    {expanded.has(o.id) && (
                      <div className="border-l-2 border-brand-300 dark:border-brand-700 ml-1.5 pl-3 mb-2 flex flex-col gap-2">
                        {o.linked_groups.map((lg) => (
                          <div key={lg.id} className="bg-gray-50 dark:bg-gray-900/60 border border-gray-200 dark:border-gray-700 rounded-lg px-2.5 py-2">
                            <div className="flex items-center gap-1.5 mb-1">
                              <span className="text-[9px] font-semibold uppercase tracking-wide text-brand-600 bg-brand-50 dark:bg-brand-950/50 dark:text-brand-300 rounded px-1.5 py-0.5">↳ Linked</span>
                              <span className="text-xs font-bold text-gray-900 dark:text-gray-100">{lg.name}</span>
                              <span className="ml-auto text-[10.5px] text-gray-400 dark:text-gray-500">choose {lg.max_selections}</span>
                              <button onClick={() => unlinkGroup.mutate({ optionId: o.id, linkedGroupId: lg.id })} className="text-gray-300 dark:text-gray-600 hover:text-red-500 text-xs">✕</button>
                            </div>
                            {lg.options.map((lo) => (
                              <div key={lo.id} className="flex items-center justify-between py-0.5 text-xs text-gray-600 dark:text-gray-300">
                                <span>{lo.name}</span>
                                <span className="font-mono text-gray-900 dark:text-gray-100">+{centsToDisplay(lo.price_delta_cents)}</span>
                              </div>
                            ))}
                          </div>
                        ))}
                        <LinkAnotherGroup
                          allGroups={groups}
                          exclude={[g.id, ...o.linked_groups.map((lg) => lg.id)]}
                          onLink={(linkedGroupId) => linkGroup.mutate({ optionId: o.id, linkedGroupId })}
                        />
                      </div>
                    )}
                    {o.linked_groups.length === 0 && (
                      <LinkTrigger allGroups={groups} exclude={[g.id]} onLink={(linkedGroupId) => linkGroup.mutate({ optionId: o.id, linkedGroupId })} />
                    )}
                  </div>
                ))}
                <button
                  onClick={() => createOption.mutate(g.id)}
                  className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 mt-1"
                >
                  + Add option
                </button>
              </div>

              <div className="bg-gray-50 dark:bg-gray-900/40 border-t border-gray-100 dark:border-gray-700 px-4 py-2.5 text-xs text-gray-400 dark:text-gray-500">
                ▸ Used by {g.used_by_count} product{g.used_by_count === 1 ? '' : 's'}
              </div>
            </div>
          ))}
          <button
            onClick={() => createGroup.mutate()}
            className="min-h-[240px] border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl flex items-center justify-center text-sm font-semibold text-gray-400 dark:text-gray-500 hover:border-brand-400 hover:text-brand-600 transition-colors"
          >
            + New modifier
          </button>
        </div>
      )}
    </div>
  )
}

interface BufferedInputProps {
  value: string
  onCommit: (value: string) => void
  type?: 'text' | 'number'
  step?: string
  min?: number
  className?: string
}

/**
 * A text/number input that edits a local draft while focused and only
 * fires onCommit on blur or Enter — never per keystroke. Directly binding
 * these inputs to server-derived values (mutate-on-every-change) caused
 * a request storm (one PATCH + full list refetch per character) and
 * visible typing lag/dropped keystrokes, since the displayed value came
 * from stale query data until each round trip resolved.
 */
function BufferedInput({ value, onCommit, type = 'text', step, min, className }: BufferedInputProps) {
  const [draft, setDraft] = useState(value)
  const [prevValue, setPrevValue] = useState(value)
  const [focused, setFocused] = useState(false)

  // Resync the draft when the server value changes externally (e.g. another
  // tab's edit refetches in) — but only while not focused, so it never
  // clobbers what the user is actively typing. Computed at render time
  // rather than in a useEffect (no external system to synchronize with —
  // same convention as CategoriesPage.tsx's reporting-group default).
  if (value !== prevValue && !focused) {
    setPrevValue(value)
    setDraft(value)
  }

  return (
    <input
      type={type}
      step={step}
      min={min}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onFocus={() => setFocused(true)}
      onBlur={() => {
        setFocused(false)
        if (draft !== value) onCommit(draft)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') e.currentTarget.blur()
        if (e.key === 'Escape') { setDraft(value); e.currentTarget.blur() }
      }}
      className={className}
    />
  )
}

/** A small "+ Link a group" ghost trigger shown on an option with no links yet. */
function LinkTrigger({ allGroups, exclude, onLink }: { allGroups: ModifierGroupDetail[]; exclude: string[]; onLink: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  const candidates = allGroups.filter((g) => !exclude.includes(g.id))
  if (candidates.length === 0) return null
  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="text-[10.5px] font-medium text-gray-300 dark:text-gray-600 hover:text-brand-600 mb-1">
        + Link a group
      </button>
    )
  }
  return <LinkAnotherGroup allGroups={allGroups} exclude={exclude} onLink={(id) => { onLink(id); setOpen(false) }} />
}

/** Ghost "+ Link another group" action with an inline dropdown of candidate groups. */
function LinkAnotherGroup({ allGroups, exclude, onLink }: { allGroups: ModifierGroupDetail[]; exclude: string[]; onLink: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  const candidates = allGroups.filter((g) => !exclude.includes(g.id))

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 border border-dashed border-gray-300 dark:border-gray-600 rounded-md px-2.5 py-1.5 text-[11px] font-semibold text-gray-500 dark:text-gray-400 hover:border-brand-400 hover:text-brand-600 self-start"
      >
        + Link another group
      </button>
    )
  }
  return (
    <select
      autoFocus
      defaultValue=""
      onChange={(e) => { if (e.target.value) onLink(e.target.value) }}
      onBlur={() => setOpen(false)}
      className="border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 rounded-md text-xs px-2 py-1.5"
    >
      <option value="" disabled>Choose a group…</option>
      {candidates.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
    </select>
  )
}
