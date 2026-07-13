/**
 * POS Menu Builder (Stage 23) — a graphical layout tool: layouts contain
 * ordered tabs, each holding ordered product buttons resolved live by ref
 * code. Reordering and cross-tab moves use native HTML5 drag-and-drop (no
 * extra dependency — none is installed in this project).
 *
 * Prototype scope: single-level tabs + buttons only, no nested sub-menus.
 * "Site ID" is a raw text field for scope='site' when the caller isn't
 * already site-scoped, mirroring the same documented workaround used on
 * management/UsersPage.tsx's grant form — no management-JWT-scoped
 * GET /sites route exists yet (Stage 17/18's flagged known limitation).
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/axios'
import { useAuth, isMgmtUser } from '../../context/AuthContext'
import { useMgmtBrandId } from '../../hooks/useMgmtBrandId'
import { Modal } from '../../components/Modal'
import { StatusBadge } from '../../components/StatusBadge'
import { EntityIdChip } from '../../components/EntityIdChip'
import { apiErrorMessage } from '../../utils/apiError'
import type { MenuLayout, MenuLayoutDetail, MenuTab, ProductListItem, PublishResult, PublishWarning } from '../../types'

function centsToDisplay(cents: number | null): string {
  return cents === null ? '—' : `$${(cents / 100).toFixed(2)}`
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
    <div className="p-4 sm:p-6 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Menu Builder</h1>
      </div>

      {selectedLayoutId ? (
        <LayoutBuilder brandId={brandId} layoutId={selectedLayoutId} onBack={() => setSelectedLayoutId(null)} />
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

  const { data: layouts = [], isLoading } = useQuery<MenuLayout[]>({
    queryKey: ['menu-layouts', brandId],
    queryFn: () => api.get('/menu-layouts', { params: { ...params, limit: 200 } }).then((r) => r.data),
  })

  const invalidateList = () => qc.invalidateQueries({ queryKey: ['menu-layouts', brandId] })

  const publish = useMutation({
    mutationFn: (layout: MenuLayout) => api.post(`/menu-layouts/${layout.id}/publish`, {}, { params }),
    onSuccess: invalidateList,
    onError: invalidateList,
  })
  const unpublish = useMutation({
    mutationFn: (layout: MenuLayout) => api.post(`/menu-layouts/${layout.id}/unpublish`, {}, { params }),
    onSuccess: invalidateList,
    onError: invalidateList,
  })
  const remove = useMutation({
    mutationFn: (layout: MenuLayout) => api.delete(`/menu-layouts/${layout.id}`, { params }),
    onSuccess: invalidateList,
    onError: invalidateList,
  })

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          onClick={() => setShowCreate(true)}
          className="bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          Add layout
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700">
          <table className="w-full text-sm min-w-[700px]">
            <thead className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-400">Name</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-400">Scope</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-400">Version</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-400">Status</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-400">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {layouts.map((layout) => (
                <tr key={layout.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/60">
                  <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">
                    <button onClick={() => onOpen(layout.id)} className="text-brand-600 hover:underline">
                      {layout.name}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-gray-700 dark:text-gray-300">
                    {layout.scope === 'brand' ? 'All sites' : <EntityIdChip id={layout.site_id ?? ''} />}
                  </td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">v{layout.version}</td>
                  <td className="px-4 py-3">
                    <StatusBadge
                      status={layout.is_published ? 'active' : 'disabled'}
                      title={layout.is_published ? 'Published — click to unpublish' : 'Draft — click to publish'}
                      onClick={() => (layout.is_published ? unpublish.mutate(layout) : publish.mutate(layout))}
                    />
                  </td>
                  <td className="px-4 py-3 flex flex-wrap gap-3">
                    <button onClick={() => onOpen(layout.id)} className="text-brand-600 hover:underline text-xs">
                      Open builder
                    </button>
                    <button
                      onClick={() => { if (confirm(`Delete layout "${layout.name}"?`)) remove.mutate(layout) }}
                      className="text-red-600 hover:underline text-xs"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {layouts.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-400 dark:text-gray-500">
                    No menu layouts yet.
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
        { name, scope, site_id: scope === 'site' ? siteId : null },
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
    <Modal title="Add menu layout" onClose={onClose}>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Main Menu, Breakfast Menu"
            autoFocus
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
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

// ── Layout builder (tabs + buttons) ─────────────────────────────────────────────

function LayoutBuilder({ brandId, layoutId, onBack }: { brandId: string; layoutId: string; onBack: () => void }) {
  const qc = useQueryClient()
  const params = { brand_id: brandId }
  const [activeTabId, setActiveTabId] = useState<string | null>(null)
  const [warnings, setWarnings] = useState<PublishWarning[] | null>(null)
  const [draggingTabId, setDraggingTabId] = useState<string | null>(null)
  const [draggingButtonId, setDraggingButtonId] = useState<string | null>(null)

  const { data: layout, isLoading } = useQuery<MenuLayoutDetail>({
    queryKey: ['menu-layout', layoutId],
    queryFn: () => api.get(`/menu-layouts/${layoutId}`, { params }).then((r) => r.data),
  })

  const { data: products = [] } = useQuery<ProductListItem[]>({
    queryKey: ['products', brandId],
    queryFn: () => api.get('/products', { params: { ...params, limit: 200 } }).then((r) => r.data),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['menu-layout', layoutId] })

  const addTab = useMutation({
    mutationFn: (name: string) => api.post(`/menu-layouts/${layoutId}/tabs`, { name }, { params }),
    onSuccess: (resp) => { invalidate(); setActiveTabId(resp.data.id) },
    onError: invalidate,
  })
  const renameTab = useMutation({
    mutationFn: ({ tabId, name }: { tabId: string; name: string }) =>
      api.patch(`/menu-layouts/${layoutId}/tabs/${tabId}`, { name }, { params }),
    onSuccess: invalidate,
    onError: invalidate,
  })
  const deleteTab = useMutation({
    mutationFn: (tabId: string) => api.delete(`/menu-layouts/${layoutId}/tabs/${tabId}`, { params }),
    onSuccess: invalidate,
    onError: invalidate,
  })
  const reorderTabs = useMutation({
    mutationFn: (tabIds: string[]) =>
      api.post(`/menu-layouts/${layoutId}/tabs/reorder`, { tab_ids: tabIds }, { params }),
    onSuccess: invalidate,
    onError: invalidate,
  })
  const addButton = useMutation({
    mutationFn: ({ tabId, productRef }: { tabId: string; productRef: string }) =>
      api.post(`/menu-layouts/${layoutId}/tabs/${tabId}/buttons`, { product_ref: productRef }, { params }),
    onSuccess: invalidate,
    onError: invalidate,
  })
  const removeButton = useMutation({
    mutationFn: ({ tabId, buttonId }: { tabId: string; buttonId: string }) =>
      api.delete(`/menu-layouts/${layoutId}/tabs/${tabId}/buttons/${buttonId}`, { params }),
    onSuccess: invalidate,
    onError: invalidate,
  })
  const reorderButtons = useMutation({
    mutationFn: ({ tabId, buttonIds }: { tabId: string; buttonIds: string[] }) =>
      api.post(`/menu-layouts/${layoutId}/tabs/${tabId}/buttons/reorder`, { button_ids: buttonIds }, { params }),
    onSuccess: invalidate,
    onError: invalidate,
  })
  const publish = useMutation({
    mutationFn: () => api.post<PublishResult>(`/menu-layouts/${layoutId}/publish`, {}, { params }),
    onSuccess: (resp) => { invalidate(); setWarnings(resp.data.warnings) },
  })
  const unpublish = useMutation({
    mutationFn: () => api.post(`/menu-layouts/${layoutId}/unpublish`, {}, { params }),
    onSuccess: invalidate,
  })

  if (isLoading || !layout) {
    return <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
  }

  const tabs = layout.tabs
  const activeTab: MenuTab | undefined = tabs.find((t) => t.id === activeTabId) ?? tabs[0]

  const handleTabDrop = (targetTabId: string) => {
    if (!draggingTabId || draggingTabId === targetTabId) return
    const order = tabs.map((t) => t.id)
    const from = order.indexOf(draggingTabId)
    const to = order.indexOf(targetTabId)
    order.splice(from, 1)
    order.splice(to, 0, draggingTabId)
    setDraggingTabId(null)
    reorderTabs.mutate(order)
  }

  const handleButtonDrop = (targetButtonId: string | null) => {
    if (!draggingButtonId || !activeTab) return
    // Build this tab's button ids, inserting the dragged button at the drop position
    // (or appending if it isn't already in this tab, i.e. a cross-tab move).
    const existingIds = activeTab.buttons.map((b) => b.id).filter((id) => id !== draggingButtonId)
    const insertAt = targetButtonId ? existingIds.indexOf(targetButtonId) : existingIds.length
    const nextIds = [...existingIds]
    nextIds.splice(insertAt === -1 ? existingIds.length : insertAt, 0, draggingButtonId)
    setDraggingButtonId(null)
    reorderButtons.mutate({ tabId: activeTab.id, buttonIds: nextIds })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button onClick={onBack} className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-900">
          ← Back to layouts
        </button>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">{layout.name}</h2>
          <StatusBadge status={layout.is_published ? 'active' : 'disabled'} title={layout.is_published ? 'Published' : 'Draft'} />
          <span className="text-xs text-gray-400 dark:text-gray-500">v{layout.version}</span>
          <button
            onClick={() => (layout.is_published ? unpublish.mutate() : publish.mutate())}
            className="bg-brand-600 hover:bg-brand-700 text-white text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
          >
            {layout.is_published ? 'Unpublish' : 'Publish'}
          </button>
        </div>
      </div>

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

      <div className="flex flex-col sm:flex-row gap-4">
        {/* Tabs sidebar */}
        <div className="sm:w-56 flex-shrink-0 space-y-2">
          <div className="flex flex-col gap-1">
            {tabs.map((tab) => (
              <div
                key={tab.id}
                draggable
                onDragStart={() => setDraggingTabId(tab.id)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => handleTabDrop(tab.id)}
                className={`flex items-center justify-between gap-2 px-3 py-2 rounded-lg text-sm cursor-move border ${
                  activeTab?.id === tab.id ? 'bg-brand-50 border-brand-200 text-brand-800' : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800/60'
                }`}
              >
                <button onClick={() => setActiveTabId(tab.id)} className="flex-1 text-left truncate">
                  {tab.name} <span className="text-gray-400 dark:text-gray-500">({tab.buttons.length})</span>
                </button>
                <button
                  onClick={() => {
                    const name = prompt('Rename tab', tab.name)
                    if (name) renameTab.mutate({ tabId: tab.id, name })
                  }}
                  className="text-gray-400 dark:text-gray-500 hover:text-gray-600 text-xs"
                  title="Rename"
                >
                  ✎
                </button>
                <button
                  onClick={() => { if (confirm(`Delete tab "${tab.name}"?`)) deleteTab.mutate(tab.id) }}
                  className="text-gray-400 dark:text-gray-500 hover:text-red-600 text-xs"
                  title="Delete"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          <button
            onClick={() => {
              const name = prompt('New tab name')
              if (name) addTab.mutate(name)
            }}
            className="w-full text-xs px-3 py-2 border border-dashed border-gray-300 dark:border-gray-600 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/60 transition-colors"
          >
            + Add tab
          </button>
        </div>

        {/* Button grid */}
        <div className="flex-1 min-w-0">
          {!activeTab ? (
            <p className="text-sm text-gray-400 dark:text-gray-500">Add a tab to start placing product buttons.</p>
          ) : (
            <ButtonGrid
              tab={activeTab}
              products={products}
              draggingButtonId={draggingButtonId}
              onDragStartButton={setDraggingButtonId}
              onDropButton={handleButtonDrop}
              onAddButton={(productRef) => addButton.mutate({ tabId: activeTab.id, productRef })}
              onRemoveButton={(buttonId) => removeButton.mutate({ tabId: activeTab.id, buttonId })}
              addError={addButton.isError ? apiErrorMessage(addButton.error, 'Failed to add button.') : null}
            />
          )}
        </div>
      </div>
    </div>
  )
}

interface ButtonGridProps {
  tab: MenuTab
  products: ProductListItem[]
  draggingButtonId: string | null
  onDragStartButton: (id: string) => void
  onDropButton: (targetButtonId: string | null) => void
  onAddButton: (productRef: string) => void
  onRemoveButton: (buttonId: string) => void
  addError: string | null
}

function ButtonGrid({
  tab,
  products,
  onDragStartButton,
  onDropButton,
  onAddButton,
  onRemoveButton,
  addError,
}: ButtonGridProps) {
  const [showPicker, setShowPicker] = useState(false)
  const [search, setSearch] = useState('')

  const matches = products.filter(
    (p) => p.is_active && (p.name.toLowerCase().includes(search.toLowerCase()) || p.ref.toLowerCase().includes(search.toLowerCase()))
  )

  return (
    <div
      className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3"
      onDragOver={(e) => e.preventDefault()}
      onDrop={() => onDropButton(null)}
    >
      {tab.buttons.map((button) => (
        <div
          key={button.id}
          draggable
          onDragStart={() => onDragStartButton(button.id)}
          onDragOver={(e) => { e.preventDefault(); e.stopPropagation() }}
          onDrop={(e) => { e.stopPropagation(); onDropButton(button.id) }}
          className={`relative border rounded-lg p-3 text-sm cursor-move bg-white dark:bg-gray-800 ${
            button.is_active === false ? 'border-red-200' : button.product_name === null ? 'border-amber-200' : 'border-gray-200 dark:border-gray-700'
          }`}
        >
          <button
            onClick={() => onRemoveButton(button.id)}
            className="absolute top-1 right-1 text-gray-300 hover:text-red-600 text-xs"
            title="Remove"
          >
            ×
          </button>
          <p className="font-medium text-gray-900 dark:text-gray-100 truncate pr-4">{button.product_name ?? 'Unknown product'}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">{centsToDisplay(button.price_cents)}</p>
          <p className="text-xs text-gray-400 dark:text-gray-500 font-mono">{button.product_ref}</p>
          {button.product_name === null && <p className="text-xs text-red-600 mt-1">Code no longer resolves</p>}
          {button.is_active === false && <p className="text-xs text-amber-600 mt-1">Product inactive</p>}
        </div>
      ))}

      <div className="border border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-3 flex items-center justify-center">
        {showPicker ? (
          <div className="w-full space-y-2">
            <input
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search products…"
              className="w-full px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-xs focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
            <div className="max-h-40 overflow-y-auto space-y-1">
              {matches.slice(0, 20).map((p) => (
                <button
                  key={p.id}
                  onClick={() => { onAddButton(p.ref); setShowPicker(false); setSearch('') }}
                  className="w-full text-left text-xs px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 truncate"
                >
                  {p.name} <span className="text-gray-400 dark:text-gray-500">({p.ref})</span>
                </button>
              ))}
              {matches.length === 0 && <p className="text-xs text-gray-400 dark:text-gray-500 px-2">No matching products.</p>}
            </div>
            <button onClick={() => setShowPicker(false)} className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600">
              Cancel
            </button>
          </div>
        ) : (
          <button onClick={() => setShowPicker(true)} className="text-xs text-gray-500 dark:text-gray-400 hover:text-brand-600">
            + Add button
          </button>
        )}
      </div>

      {addError && <p className="col-span-full text-xs text-red-600">{addError}</p>}
    </div>
  )
}
