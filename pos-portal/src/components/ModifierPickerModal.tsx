/**
 * Modal for managing a product's attached modifier groups — a reorderable
 * "Attached" list (native HTML5 drag-and-drop) plus an "Add more" checklist of
 * available groups. Self-contained: fetches GET /products/{id}/modifiers on
 * mount and PATCHes the full ordered set to /products/{id}/modifiers/reorder
 * on "Done".
 *
 * Props are kept generic ({ productId, productName, onClose, onSaved }) so a
 * future modifier-group-centric usage (e.g. "used by products" on the
 * Modifiers tab) can reuse this component without depending on any
 * ProductsPage-local state.
 */

import { useEffect, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '../api/axios'
import { useMgmtBrandId } from '../hooks/useMgmtBrandId'
import { Modal } from './Modal'
import { apiErrorMessage } from '../utils/apiError'

/** One modifier group already attached to the product, in display order. */
interface AttachedItem {
  modifier_group_id: string
  name: string
  option_count: number
  display_order: number
}

/** One active modifier group in the brand not yet attached to this product. */
interface AvailableItem {
  modifier_group_id: string
  name: string
  option_count: number
}

interface ProductModifiersOut {
  attached: AttachedItem[]
  available: AvailableItem[]
}

interface Props {
  productId: string
  productName: string
  onClose: () => void
  onSaved: () => void
}

export function ModifierPickerModal({ productId, productName, onClose, onSaved }: Props) {
  const brandId = useMgmtBrandId()
  const params = brandId ? { brand_id: brandId } : {}

  const { data, isLoading } = useQuery<ProductModifiersOut>({
    queryKey: ['product-modifiers', productId],
    queryFn: () => api.get(`/products/${productId}/modifiers`, { params }).then((r) => r.data),
  })

  // Local working copy of the attached list (ids in display order) — edited
  // via drag-reorder / remove / add-more, then PATCHed as a single reorder
  // call on "Done".
  const [attachedIds, setAttachedIds] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [dragIndex, setDragIndex] = useState<number | null>(null)

  // Sync local state once the fetch resolves (data.attached arrives already
  // ordered by display_order).
  useEffect(() => {
    if (data) setAttachedIds(data.attached.map((a) => a.modifier_group_id))
  }, [data])

  // Lookup map of every known group (attached + available) so the attached
  // list can render name/option_count purely from ids after local reordering.
  const groupById = new Map<string, { name: string; option_count: number }>()
  data?.attached.forEach((a) => groupById.set(a.modifier_group_id, a))
  data?.available.forEach((a) => groupById.set(a.modifier_group_id, a))

  const availableNotAttached = (data?.available ?? []).filter((a) => !attachedIds.includes(a.modifier_group_id))

  const removeAttached = (id: string) => setAttachedIds((prev) => prev.filter((x) => x !== id))
  const addAttached = (id: string) => setAttachedIds((prev) => [...prev, id])

  const handleDrop = (targetIndex: number) => {
    if (dragIndex === null || dragIndex === targetIndex) return
    setAttachedIds((prev) => {
      const next = [...prev]
      const [moved] = next.splice(dragIndex, 1)
      next.splice(targetIndex, 0, moved)
      return next
    })
    setDragIndex(null)
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      api.patch(`/products/${productId}/modifiers/reorder`, { modifier_group_ids: attachedIds }, { params }),
    onSuccess: () => {
      onSaved()
      onClose()
    },
    onError: (e: unknown) => setError(apiErrorMessage(e, 'Failed to save modifier sets.')),
  })

  return (
    <Modal title={`Modifier sets — ${productName}`} onClose={onClose}>
      {isLoading ? (
        <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
      ) : (
        <div className="space-y-5">
          <div>
            <p className="text-xs font-semibold tracking-wide text-gray-500 dark:text-gray-400 mb-2">
              ATTACHED &middot; DRAG TO REORDER (THIS IS THE POS DISPLAY ORDER)
            </p>
            <div className="space-y-1">
              {attachedIds.map((id, index) => {
                const g = groupById.get(id)
                return (
                  <div
                    key={id}
                    draggable
                    onDragStart={() => setDragIndex(index)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={() => handleDrop(index)}
                    className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 cursor-move"
                  >
                    <span className="flex items-center gap-2 min-w-0">
                      <span className="text-gray-300 dark:text-gray-600 select-none">⠿</span>
                      <span className="truncate text-sm text-gray-900 dark:text-gray-100">{g?.name ?? id}</span>
                      <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0">
                        {g?.option_count ?? 0} option{(g?.option_count ?? 0) === 1 ? '' : 's'}
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => removeAttached(id)}
                      title="Remove"
                      className="text-gray-400 hover:text-red-600 dark:text-gray-500 dark:hover:text-red-400 text-sm leading-none px-1"
                    >
                      ×
                    </button>
                  </div>
                )
              })}
              {attachedIds.length === 0 && (
                <p className="text-sm text-gray-400 dark:text-gray-500 px-1 py-2">No modifier sets attached.</p>
              )}
            </div>
          </div>

          <div>
            <p className="text-xs font-semibold tracking-wide text-gray-500 dark:text-gray-400 mb-2">ADD MORE</p>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {availableNotAttached.map((a) => (
                <label
                  key={a.modifier_group_id}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    className="zr-chk"
                    checked={false}
                    onChange={() => addAttached(a.modifier_group_id)}
                  />
                  <span className="text-sm text-gray-900 dark:text-gray-100">{a.name}</span>
                  <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">
                    {a.option_count} option{a.option_count === 1 ? '' : 's'}
                  </span>
                </label>
              ))}
              {availableNotAttached.length === 0 && (
                <p className="text-sm text-gray-400 dark:text-gray-500 px-1 py-2">No more modifier sets available.</p>
              )}
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100">
              Cancel
            </button>
            <button
              onClick={() => { setError(null); saveMutation.mutate() }}
              disabled={saveMutation.isPending}
              className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {saveMutation.isPending ? 'Saving…' : 'Done'}
            </button>
          </div>
        </div>
      )}
    </Modal>
  )
}
