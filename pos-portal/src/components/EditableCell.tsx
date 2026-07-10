/** Inline-editable table cells (Stage 20) — click a text cell to edit, pick a select inline. */

import { useRef, useState } from 'react'
import { apiErrorMessage } from '../utils/apiError'

interface EditableTextProps {
  value: string
  onSave: (newValue: string) => Promise<void>
  type?: 'text' | 'number'
  disabled?: boolean
  emptyLabel?: string
  formatDisplay?: (value: string) => React.ReactNode
}

/** Click-to-edit text/number cell. Saves on blur or Enter; Escape reverts without saving. */
export function EditableText({ value, onSave, type = 'text', disabled, emptyLabel = '—', formatDisplay }: EditableTextProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const cancelingRef = useRef(false)

  const display = formatDisplay ? formatDisplay(value) : (value || <span className="text-gray-300 italic">{emptyLabel}</span>)

  if (disabled) {
    return <span>{display}</span>
  }

  const commit = async () => {
    if (draft === value) {
      setEditing(false)
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onSave(draft)
      setEditing(false)
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'Failed to save.'))
    } finally {
      setSaving(false)
    }
  }

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => { setDraft(value); setEditing(true) }}
        title="Click to edit"
        className="text-left w-full hover:bg-gray-100 rounded px-1.5 py-0.5 -mx-1.5 transition-colors"
      >
        {display}
      </button>
    )
  }

  return (
    <div className="min-w-[100px]">
      <input
        autoFocus
        type={type}
        step={type === 'number' ? '0.01' : undefined}
        value={draft}
        disabled={saving}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          if (cancelingRef.current) {
            cancelingRef.current = false
            return
          }
          commit()
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur()
          if (e.key === 'Escape') {
            cancelingRef.current = true
            setDraft(value)
            setEditing(false)
            setError(null)
          }
        }}
        className="w-full px-2 py-1 border border-brand-400 rounded text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
      />
      {error && <p className="text-xs text-red-600 mt-1 whitespace-nowrap">{error}</p>}
    </div>
  )
}

interface EditableSelectProps {
  value: string
  options: { value: string; label: string }[]
  onSave: (newValue: string) => Promise<void>
  disabled?: boolean
}

/** Always-inline select cell — commits immediately on change. */
export function EditableSelect({ value, options, onSave, disabled }: EditableSelectProps) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (disabled) {
    return <span>{options.find((o) => o.value === value)?.label ?? value}</span>
  }

  return (
    <div className="min-w-[120px]">
      <select
        value={value}
        disabled={saving}
        onChange={async (e) => {
          const newValue = e.target.value
          if (newValue === value) return
          setSaving(true)
          setError(null)
          try {
            await onSave(newValue)
          } catch (err: unknown) {
            setError(apiErrorMessage(err, 'Failed to save.'))
          } finally {
            setSaving(false)
          }
        }}
        className="w-full px-2 py-1 border border-gray-200 hover:border-gray-300 rounded text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      {error && <p className="text-xs text-red-600 mt-1 whitespace-nowrap">{error}</p>}
    </div>
  )
}
