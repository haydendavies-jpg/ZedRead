/**
 * Floor-map editor (Android POS Phase 4 — table maps & floor service).
 *
 * Architecturally mirrors MenuBuilderPage.tsx's POS Layout grid editor
 * (list view + pointer-based canvas editor + single-selection inspector),
 * per ANDROID_POS_BUILD_PLAN.md's Phase 4 section — but the canvas is a
 * free-form percentage-of-stage (x/y/w/h all 0-100 floats, matching
 * TableMapShapeCreate) rather than MenuBuilderPage's discrete 6-column grid,
 * since table maps have no fixed cell size. Multi-select and its floating
 * action bar are intentionally not carried over — table maps only need a
 * single-selection inspector (see the task spec's "keep it simpler").
 */

import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, fetchAll } from '../../api/axios'
import { useAuth, isMgmtUser } from '../../context/AuthContext'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { Modal } from '../../components/Modal'
import { ColorSwatchPicker } from '../../components/ColorSwatchPicker'
import { apiErrorMessage } from '../../utils/apiError'
import type { Site, TableMap, TableMapDetail, TableMapShape, TableMapShapeKind } from '../../types'

// Mirrors app/constants/table_map.py's SHAPE_KINDS split — table-kind shapes
// each get a 1:1 DiningTable row (dining_table_id, read-only here); decor
// shapes render the floor plan's backdrop only.
const TABLE_SHAPE_KINDS: TableMapShapeKind[] = ['stool', 'round', 'rect']
const DECOR_SHAPE_KINDS: TableMapShapeKind[] = ['zone', 'bar_counter', 'entrance', 'wall']

const SHAPE_LABELS: Record<TableMapShapeKind, string> = {
  stool: 'Stool',
  round: 'Round table',
  rect: 'Rect table',
  zone: 'Zone',
  bar_counter: 'Bar counter',
  entrance: 'Entrance',
  wall: 'Wall',
}

/** Default placement/size (percent-of-stage) for a newly-added shape, dropped near the stage centre. */
function defaultsForKind(kind: TableMapShapeKind): { x: number; y: number; w: number; h: number; dashed: boolean } {
  if (TABLE_SHAPE_KINDS.includes(kind)) return { x: 40, y: 40, w: 10, h: 10, dashed: false }
  if (kind === 'zone') return { x: 30, y: 30, w: 30, h: 25, dashed: true }
  if (kind === 'bar_counter') return { x: 20, y: 10, w: 35, h: 8, dashed: false }
  if (kind === 'entrance') return { x: 45, y: 92, w: 10, h: 6, dashed: false }
  return { x: 10, y: 10, w: 25, h: 3, dashed: false } // wall
}

const DEFAULT_TABLE_COLOR = '#4E7A51'
const DEFAULT_DECOR_COLOR = '#5A5550'

const clamp = (v: number, min: number, max: number) => Math.min(Math.max(v, min), max)

/** Round to the nearest grid_size multiple, clamped to [0, 100]. Used only when is_grid_locked. */
function snapToGrid(value: number, gridSize: number): number {
  if (gridSize <= 0) return value
  return clamp(Math.round(value / gridSize) * gridSize, 0, 100)
}

export function TableMapsPage() {
  const brandId = useMgmtBrandId()
  const [selectedMapId, setSelectedMapId] = useState<string | null>(null)

  if (!brandId) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-gray-400 dark:text-gray-500">
        No brand context available.
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 space-y-4" style={{ fontFamily: "'IBM Plex Sans', sans-serif" }}>
      {selectedMapId ? (
        <MapEditor brandId={brandId} mapId={selectedMapId} onBack={() => setSelectedMapId(null)} />
      ) : (
        <MapsList brandId={brandId} onOpen={setSelectedMapId} />
      )}
    </div>
  )
}

// ── Maps list ────────────────────────────────────────────────────────────────

function MapsList({ brandId, onOpen }: { brandId: string; onOpen: (id: string) => void }) {
  const qc = useQueryClient()
  const params = { brand_id: brandId }
  const [showCreate, setShowCreate] = useState(false)
  const [siteFilter, setSiteFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)

  const { data: maps = [], isLoading } = useQuery<TableMap[]>({
    queryKey: ['table-maps', brandId],
    queryFn: () => fetchAll<TableMap>('/table-maps', params),
  })
  const { data: sites = [] } = useQuery<Site[]>({
    queryKey: ['sites-for-brand', brandId],
    queryFn: () => fetchAll<Site>('/sites', { brand_id: brandId }),
  })
  const siteName = (id: string) => sites.find((s) => s.id === id)?.name ?? id.slice(0, 8)

  const invalidateList = () => qc.invalidateQueries({ queryKey: ['table-maps', brandId] })
  const onActionError = (e: unknown) => { invalidateList(); setActionError(apiErrorMessage(e, 'Action failed.')) }

  const publish = useMutation({
    mutationFn: (m: TableMap) => api.post(`/table-maps/${m.id}/publish`, {}, { params }),
    onSuccess: invalidateList,
    onError: onActionError,
  })
  const unpublish = useMutation({
    mutationFn: (m: TableMap) => api.post(`/table-maps/${m.id}/unpublish`, {}, { params }),
    onSuccess: invalidateList,
    onError: onActionError,
  })
  const duplicate = useMutation({
    mutationFn: (m: TableMap) => api.post(`/table-maps/${m.id}/duplicate`, {}, { params }),
    onSuccess: invalidateList,
    onError: onActionError,
  })
  const remove = useMutation({
    mutationFn: (m: TableMap) => api.delete(`/table-maps/${m.id}`, { params }),
    onSuccess: invalidateList,
    onError: onActionError,
  })

  const filtered = maps.filter((m) => {
    if (siteFilter && m.site_id !== siteFilter) return false
    if (statusFilter === 'published' && !m.is_published) return false
    if (statusFilter === 'unpublished' && m.is_published) return false
    return true
  })
  const hasFilters = siteFilter || statusFilter

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-serif font-bold text-[22px] text-gray-900 dark:text-gray-100 leading-tight">Table Maps</h1>
          <p className="text-[11px] font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500 mt-0.5">
            {maps.length} {maps.length === 1 ? 'map' : 'maps'}
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-3 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
        >
          + New map
        </button>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Site</label>
          <select
            value={siteFilter}
            onChange={(e) => setSiteFilter(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="">All sites</option>
            {sites.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Status</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="">Any</option>
            <option value="published">Published</option>
            <option value="unpublished">Unpublished</option>
          </select>
        </div>
        {hasFilters && (
          <button onClick={() => { setSiteFilter(''); setStatusFilter('') }} className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600">
            Clear filters
          </button>
        )}
        <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">{filtered.length} of {maps.length}</span>
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
          <table className="zr-table min-w-[720px]">
            <thead>
              <tr>
                <th>Map</th>
                <th>Site</th>
                <th>Status</th>
                <th className="zr-num">Shapes</th>
                <th>Last edited</th>
                <th className="zr-num">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((m) => (
                <tr key={m.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/60 cursor-pointer" onClick={() => onOpen(m.id)}>
                  <td className="px-4 py-3 font-semibold text-gray-900 dark:text-gray-100">{m.name}</td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{siteName(m.site_id)}</td>
                  <td className="px-4 py-3">
                    <span className={`zr-pill ${m.is_published ? 'zr-pill--live' : 'zr-pill--draft'}`}>
                      {m.is_published ? 'Published' : 'Unpublished'}
                    </span>
                  </td>
                  <td className="px-4 py-3 zr-num font-mono">{m.shape_count}</td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                    <div>{new Date(m.updated_at).toLocaleDateString()}</div>
                    <div className="text-[11px] text-gray-400 dark:text-gray-500">{new Date(m.updated_at).toLocaleTimeString()}</div>
                  </td>
                  <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-end flex-wrap gap-1.5">
                      <button onClick={() => onOpen(m.id)} className="px-2.5 py-1.5 bg-brand-600 text-white text-xs font-semibold rounded-md hover:bg-brand-700">
                        Edit
                      </button>
                      <button
                        onClick={() => (m.is_published ? unpublish.mutate(m) : publish.mutate(m))}
                        className="px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-semibold text-gray-600 dark:text-gray-300 rounded-md"
                      >
                        {m.is_published ? 'Unpublish' : 'Publish'}
                      </button>
                      <button onClick={() => duplicate.mutate(m)} className="px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-semibold text-gray-600 dark:text-gray-300 rounded-md">
                        ⧉ Duplicate
                      </button>
                      <button
                        onClick={() => { if (confirm(`Delete map "${m.name}"?`)) remove.mutate(m) }}
                        className="px-2.5 py-1.5 border border-red-200 dark:border-red-800 text-xs font-semibold text-red-600 dark:text-red-400 rounded-md"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-400 dark:text-gray-500">
                    {maps.length === 0 ? 'No table maps yet.' : 'No maps match the current filters.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <CreateMapModal
          brandId={brandId}
          onClose={() => setShowCreate(false)}
          onSaved={(id) => { invalidateList(); setShowCreate(false); onOpen(id) }}
        />
      )}
    </div>
  )
}

function CreateMapModal({ brandId, onClose, onSaved }: { brandId: string; onClose: () => void; onSaved: (id: string) => void }) {
  const { user } = useAuth()
  const mgmtSiteId = isMgmtUser(user) ? user.site_id ?? null : null
  const needsSiteSelector = !mgmtSiteId

  const { data: sites = [] } = useQuery<Site[]>({
    queryKey: ['sites-for-brand', brandId],
    queryFn: () => fetchAll<Site>('/sites', { brand_id: brandId }),
    enabled: needsSiteSelector,
  })

  const [name, setName] = useState('')
  const [siteId, setSiteId] = useState(mgmtSiteId ?? '')
  const [gridSize, setGridSize] = useState(20)
  const [isGridLocked, setIsGridLocked] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const resp = await api.post(
        '/table-maps',
        { name, site_id: siteId, grid_size: gridSize, is_grid_locked: isGridLocked },
        { params: { brand_id: brandId } },
      )
      onSaved(resp.data.id)
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'Failed to create map.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="Add table map" onClose={onClose}>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Main Dining Room"
            autoFocus
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Site</label>
          {mgmtSiteId ? (
            <input
              value={sites.find((s) => s.id === mgmtSiteId)?.name ?? mgmtSiteId}
              disabled
              className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 rounded-lg text-sm text-gray-500 dark:text-gray-400"
            />
          ) : (
            <select
              value={siteId}
              onChange={(e) => setSiteId(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="">Choose a site…</option>
              {sites.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          )}
        </div>
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Grid size (%)</label>
            <input
              type="number"
              min={1}
              max={100}
              value={gridSize}
              onChange={(e) => setGridSize(Number(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 pb-2.5">
            <input type="checkbox" checked={isGridLocked} onChange={(e) => setIsGridLocked(e.target.checked)} />
            Start grid-locked
          </label>
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
            disabled={saving || !name || !siteId}
            className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

// ── Canvas editor ────────────────────────────────────────────────────────────

const STAGE_BASE_WIDTH = 900
const STAGE_ASPECT = 10 / 16 // matches the design reference's aspect-ratio: 16/10 stage

function MapEditor({ brandId, mapId, onBack }: { brandId: string; mapId: string; onBack: () => void }) {
  const qc = useQueryClient()
  const params = { brand_id: brandId }
  const stageRef = useRef<HTMLDivElement>(null)

  const [selectedShapeId, setSelectedShapeId] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [actionError, setActionError] = useState<string | null>(null)
  // Live values shown during an in-progress drag/resize, before the PATCH that
  // commits it — keeps the tile following the pointer without round-tripping
  // to the server on every pointermove (same live-preview-then-commit idea
  // MenuBuilderPage's resize handles use).
  const [livePreview, setLivePreview] = useState<{ id: string; x: number; y: number; w: number; h: number } | null>(null)

  const { data: mapDetail, isLoading } = useQuery<TableMapDetail>({
    queryKey: ['table-map', mapId],
    queryFn: () => api.get(`/table-maps/${mapId}`, { params }).then((r) => r.data),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['table-map', mapId] })
  const onMutErr = (e: unknown) => { invalidate(); setActionError(apiErrorMessage(e, 'Action failed.')) }

  const patchShapeInCache = (shape: TableMapShape) => {
    qc.setQueryData<TableMapDetail>(['table-map', mapId], (old) =>
      old ? { ...old, shapes: old.shapes.map((s) => (s.id === shape.id ? shape : s)) } : old,
    )
  }

  const createShape = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post<TableMapShape>(`/table-maps/${mapId}/shapes`, body, { params }),
    onSuccess: (resp) => {
      qc.setQueryData<TableMapDetail>(['table-map', mapId], (old) =>
        old ? { ...old, shapes: [...old.shapes, resp.data], shape_count: old.shapes.length + 1 } : old,
      )
      setSelectedShapeId(resp.data.id)
    },
    onError: onMutErr,
  })
  const updateShape = useMutation({
    mutationFn: ({ shapeId, body }: { shapeId: string; body: Record<string, unknown> }) =>
      api.patch<TableMapShape>(`/table-maps/${mapId}/shapes/${shapeId}`, body, { params }),
    onSuccess: (resp) => patchShapeInCache(resp.data),
    onError: onMutErr,
  })
  const deleteShape = useMutation({
    mutationFn: (shapeId: string) => api.delete(`/table-maps/${mapId}/shapes/${shapeId}`, { params }),
    onSuccess: (_resp, shapeId) => {
      qc.setQueryData<TableMapDetail>(['table-map', mapId], (old) =>
        old ? { ...old, shapes: old.shapes.filter((s) => s.id !== shapeId), shape_count: Math.max(0, old.shapes.length - 1) } : old,
      )
      setSelectedShapeId(null)
    },
    onError: onMutErr,
  })
  const updateMap = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch<TableMap>(`/table-maps/${mapId}`, body, { params }),
    onSuccess: (resp) => {
      qc.setQueryData<TableMapDetail>(['table-map', mapId], (old) => (old ? { ...old, ...resp.data } : old))
    },
    onError: onMutErr,
  })
  const publish = useMutation({
    mutationFn: () => api.post<TableMap>(`/table-maps/${mapId}/publish`, {}, { params }),
    onSuccess: (resp) => qc.setQueryData<TableMapDetail>(['table-map', mapId], (old) => (old ? { ...old, ...resp.data } : old)),
    onError: onMutErr,
  })
  const unpublish = useMutation({
    mutationFn: () => api.post<TableMap>(`/table-maps/${mapId}/unpublish`, {}, { params }),
    onSuccess: (resp) => qc.setQueryData<TableMapDetail>(['table-map', mapId], (old) => (old ? { ...old, ...resp.data } : old)),
    onError: onMutErr,
  })

  if (isLoading || !mapDetail) {
    return <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
  }

  const gridSize = mapDetail.grid_size
  const isGridLocked = mapDetail.is_grid_locked
  const selectedShape = mapDetail.shapes.find((s) => s.id === selectedShapeId) ?? null

  const shapeAt = (id: string, fallback: TableMapShape) => (livePreview?.id === id ? { ...fallback, ...livePreview } : fallback)

  const addShape = (kind: TableMapShapeKind) => {
    const d = defaultsForKind(kind)
    const isTable = TABLE_SHAPE_KINDS.includes(kind)
    // Count existing shapes of this kind so the default label increments (Table 1, Table 2, …).
    const countOfKind = mapDetail.shapes.filter((s) => s.kind === kind).length + 1
    createShape.mutate({
      kind,
      label: isTable ? `${SHAPE_LABELS[kind]} ${countOfKind}` : `${SHAPE_LABELS[kind]} ${countOfKind}`,
      x: d.x,
      y: d.y,
      w: d.w,
      h: d.h,
      dashed: d.dashed,
      color: isTable ? DEFAULT_TABLE_COLOR : DEFAULT_DECOR_COLOR,
    })
  }

  const handleShapeDragStart = (e: React.PointerEvent, shape: TableMapShape) => {
    if (e.button !== 0) return
    e.stopPropagation()
    setSelectedShapeId(shape.id)
    if (shape.is_locked) return // locked shapes are selectable (to inspect/unlock) but not draggable
    e.preventDefault()
    const stageEl = stageRef.current
    if (!stageEl) return
    const rect = stageEl.getBoundingClientRect()
    const startX = e.clientX
    const startY = e.clientY
    const startShapeX = shape.x
    const startShapeY = shape.y
    let moved = false
    let final = { x: startShapeX, y: startShapeY }

    const onMove = (ev: PointerEvent) => {
      moved = true
      const dxPct = ((ev.clientX - startX) / rect.width) * 100
      const dyPct = ((ev.clientY - startY) / rect.height) * 100
      let nx = clamp(startShapeX + dxPct, 0, 100 - shape.w)
      let ny = clamp(startShapeY + dyPct, 0, 100 - shape.h)
      if (isGridLocked) {
        nx = clamp(snapToGrid(nx, gridSize), 0, 100 - shape.w)
        ny = clamp(snapToGrid(ny, gridSize), 0, 100 - shape.h)
      }
      final = { x: nx, y: ny }
      setLivePreview({ id: shape.id, x: nx, y: ny, w: shape.w, h: shape.h })
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      setLivePreview(null)
      if (moved && (final.x !== startShapeX || final.y !== startShapeY)) {
        updateShape.mutate({ shapeId: shape.id, body: { x: final.x, y: final.y } })
      }
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  const handleResizeStart = (e: React.PointerEvent, shape: TableMapShape) => {
    e.stopPropagation()
    e.preventDefault()
    const stageEl = stageRef.current
    if (!stageEl || shape.is_locked) return
    const rect = stageEl.getBoundingClientRect()
    const startX = e.clientX
    const startY = e.clientY
    const startW = shape.w
    const startH = shape.h
    let final = { w: startW, h: startH }

    const onMove = (ev: PointerEvent) => {
      const dwPct = ((ev.clientX - startX) / rect.width) * 100
      const dhPct = ((ev.clientY - startY) / rect.height) * 100
      let nw = clamp(startW + dwPct, 2, 100 - shape.x)
      let nh = clamp(startH + dhPct, 2, 100 - shape.y)
      if (isGridLocked) {
        nw = clamp(snapToGrid(nw, gridSize) || gridSize, 2, 100 - shape.x)
        nh = clamp(snapToGrid(nh, gridSize) || gridSize, 2, 100 - shape.y)
      }
      final = { w: nw, h: nh }
      setLivePreview({ id: shape.id, x: shape.x, y: shape.y, w: nw, h: nh })
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      setLivePreview(null)
      if (final.w !== startW || final.h !== startH) {
        updateShape.mutate({ shapeId: shape.id, body: { w: final.w, h: final.h } })
      }
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  const stageWidth = STAGE_BASE_WIDTH * zoom
  const stageHeight = stageWidth * STAGE_ASPECT

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button onClick={onBack} className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100">
          ‹ Maps
        </button>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">{mapDetail.name}</h2>
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
              mapDetail.is_published ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
            }`}
          >
            {mapDetail.is_published ? 'Published' : 'Unpublished'}
          </span>
          <button
            onClick={() => (mapDetail.is_published ? unpublish.mutate() : publish.mutate())}
            className="bg-brand-600 hover:bg-brand-700 text-white text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
          >
            {mapDetail.is_published ? 'Unpublish' : 'Publish'}
          </button>
        </div>
      </div>

      {actionError && (
        <p className="text-sm text-red-600 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">
          {actionError}
        </p>
      )}

      <div className="flex border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden" style={{ minHeight: 520 }}>
        {/* Toolbar rail — add-shape buttons + snap-to-grid + zoom controls. */}
        <div className="w-56 shrink-0 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 flex flex-col overflow-auto p-3 gap-4">
          <div>
            <div className="text-[10.5px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Tables</div>
            <div className="grid grid-cols-1 gap-1.5">
              {TABLE_SHAPE_KINDS.map((k) => (
                <button
                  key={k}
                  onClick={() => addShape(k)}
                  className="text-left text-xs px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-white dark:hover:bg-gray-800"
                >
                  + {SHAPE_LABELS[k]}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="text-[10.5px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Decor</div>
            <div className="grid grid-cols-1 gap-1.5">
              {DECOR_SHAPE_KINDS.map((k) => (
                <button
                  key={k}
                  onClick={() => addShape(k)}
                  className="text-left text-xs px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-white dark:hover:bg-gray-800"
                >
                  + {SHAPE_LABELS[k]}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="text-[10.5px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Grid</div>
            <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300 mb-2">
              <input
                type="checkbox"
                checked={isGridLocked}
                onChange={(e) => updateMap.mutate({ is_grid_locked: e.target.checked })}
              />
              Snap to grid ({gridSize}%)
            </label>
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-gray-400 dark:text-gray-500">Size</span>
              <input
                type="number"
                min={1}
                max={100}
                value={gridSize}
                onChange={(e) => updateMap.mutate({ grid_size: Number(e.target.value) })}
                className="w-16 px-2 py-1 border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 rounded-md text-xs"
              />
            </div>
          </div>
          <div>
            <div className="text-[10.5px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Zoom</div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setZoom((z) => Math.max(0.5, Math.round((z - 0.1) * 10) / 10))}
                className="w-7 h-7 border border-gray-300 dark:border-gray-600 rounded-md text-gray-600 dark:text-gray-300"
              >
                −
              </button>
              <span className="text-xs font-medium text-gray-600 dark:text-gray-300 w-10 text-center">{Math.round(zoom * 100)}%</span>
              <button
                onClick={() => setZoom((z) => Math.min(2, Math.round((z + 0.1) * 10) / 10))}
                className="w-7 h-7 border border-gray-300 dark:border-gray-600 rounded-md text-gray-600 dark:text-gray-300"
              >
                +
              </button>
            </div>
          </div>
          <div className="flex-1" />
          <p className="text-[11px] text-gray-400 dark:text-gray-500 leading-relaxed">
            Click a shape to select it. Drag to move, drag the corner handle to resize. Locked shapes can be
            selected but not moved.
          </p>
        </div>

        {/* Stage */}
        <div className="flex-1 min-w-0 overflow-auto p-4 bg-gray-100 dark:bg-gray-950 flex items-start justify-center">
          <div
            ref={stageRef}
            onClick={() => setSelectedShapeId(null)}
            className="relative bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shrink-0"
            style={{ width: stageWidth, height: stageHeight }}
          >
            {mapDetail.shapes.map((raw) => {
              const shape = shapeAt(raw.id, raw)
              const isSel = selectedShapeId === shape.id
              const isTable = TABLE_SHAPE_KINDS.includes(shape.kind)
              const bg = shape.color ?? (isTable ? DEFAULT_TABLE_COLOR : DEFAULT_DECOR_COLOR)
              const isCircular = shape.kind === 'round' || shape.kind === 'stool'
              return (
                <div
                  key={shape.id}
                  onPointerDown={(e) => handleShapeDragStart(e, raw)}
                  className={`absolute flex items-center justify-center text-center select-none touch-none ${
                    shape.is_locked ? 'cursor-not-allowed' : 'cursor-move'
                  } ${isSel ? 'ring-[3px] ring-brand-600 z-10' : ''}`}
                  style={{
                    left: `${shape.x}%`,
                    top: `${shape.y}%`,
                    width: `${shape.w}%`,
                    height: `${shape.h}%`,
                    background: shape.dashed ? 'rgba(90,85,80,0.08)' : bg,
                    border: shape.dashed ? `2px dashed ${bg}` : '2px solid rgba(0,0,0,0.15)',
                    borderRadius: isCircular ? '50%' : 10,
                  }}
                  title={shape.label}
                >
                  <span
                    className="px-1 text-[11px] font-semibold leading-tight break-words"
                    style={{ color: shape.dashed ? bg : '#ffffff' }}
                  >
                    {shape.label}
                  </span>
                  {shape.is_locked && (
                    <span className="absolute top-0.5 right-0.5 text-[10px] opacity-80" style={{ color: shape.dashed ? bg : '#ffffff' }}>
                      🔒
                    </span>
                  )}
                  {isSel && !shape.is_locked && (
                    <div
                      onPointerDown={(e) => handleResizeStart(e, raw)}
                      className="absolute bottom-0 right-0 w-4 h-4 cursor-nwse-resize flex items-end justify-end opacity-80 text-[12px] text-white z-10"
                    >
                      ⟌
                    </div>
                  )}
                </div>
              )
            })}
            {mapDetail.shapes.length === 0 && (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-gray-400 dark:text-gray-500">
                Add a table or decor shape from the left to start laying out this floor.
              </div>
            )}
          </div>
        </div>

        {/* Inspector */}
        {selectedShape && (
          <ShapeInspector
            shape={selectedShape}
            onLabel={(label) => updateShape.mutate({ shapeId: selectedShape.id, body: { label } })}
            onColor={(color) => updateShape.mutate({ shapeId: selectedShape.id, body: { color } })}
            onToggleLocked={(is_locked) => updateShape.mutate({ shapeId: selectedShape.id, body: { is_locked } })}
            onToggleDashed={(dashed) => updateShape.mutate({ shapeId: selectedShape.id, body: { dashed } })}
            onDelete={() => { if (confirm(`Delete "${selectedShape.label}"?`)) deleteShape.mutate(selectedShape.id) }}
          />
        )}
      </div>
    </div>
  )
}

function ShapeInspector({
  shape,
  onLabel,
  onColor,
  onToggleLocked,
  onToggleDashed,
  onDelete,
}: {
  shape: TableMapShape
  onLabel: (label: string) => void
  onColor: (color: string) => void
  onToggleLocked: (locked: boolean) => void
  onToggleDashed: (dashed: boolean) => void
  onDelete: () => void
}) {
  const isTable = TABLE_SHAPE_KINDS.includes(shape.kind)
  const color = shape.color ?? (isTable ? DEFAULT_TABLE_COLOR : DEFAULT_DECOR_COLOR)

  return (
    <div className="w-72 shrink-0 bg-white dark:bg-gray-800 border-l border-gray-200 dark:border-gray-700 p-4 overflow-auto flex flex-col gap-4">
      <div>
        <div className="text-[10.5px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-1.5">Shape</div>
        <p className="text-sm text-gray-700 dark:text-gray-300">{SHAPE_LABELS[shape.kind]}</p>
        {shape.dining_table_id && (
          <p className="text-[11px] text-gray-400 dark:text-gray-500 font-mono mt-0.5">Table {shape.dining_table_id.slice(0, 8)}</p>
        )}
      </div>

      <div>
        <div className="text-[10.5px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-1.5">Label</div>
        <input
          defaultValue={shape.label}
          key={shape.id}
          onBlur={(e) => { if (e.target.value && e.target.value !== shape.label) onLabel(e.target.value) }}
          className="w-full px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded-lg text-sm"
        />
      </div>

      <div>
        <div className="text-[10.5px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-1.5">Colour</div>
        <ColorSwatchPicker value={color} onChange={onColor} title="Shape colour" />
      </div>

      <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
        <input type="checkbox" checked={shape.is_locked} onChange={(e) => onToggleLocked(e.target.checked)} />
        Locked (prevents drag/resize)
      </label>

      <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
        <input type="checkbox" checked={shape.dashed} onChange={(e) => onToggleDashed(e.target.checked)} />
        Dashed outline
      </label>

      <div className="text-[11px] text-gray-400 dark:text-gray-500 font-mono">
        x {shape.x.toFixed(1)}% · y {shape.y.toFixed(1)}% · w {shape.w.toFixed(1)}% · h {shape.h.toFixed(1)}%
      </div>

      <div className="flex-1" />
      <button onClick={onDelete} className="w-full text-center text-xs font-semibold px-2.5 py-1.5 rounded-md border border-brand-300 dark:border-brand-700 text-brand-600 dark:text-brand-400">
        Delete shape
      </button>
    </div>
  )
}
