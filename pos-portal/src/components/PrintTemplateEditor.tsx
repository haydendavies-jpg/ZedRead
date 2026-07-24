/**
 * Print template editor — a reorderable list of fields (drag-to-reorder, the
 * same native HTML5 DnD technique MenuBuilderPage.tsx uses for tabs/buttons),
 * each with alignment/bold/italic/font-size, plus a live preview rendered at
 * the printer's real fixed character width using the exact same
 * alignment/padding logic (src/utils/printTemplateLayout.ts) the Android
 * renderer applies — not CSS text-align, which wouldn't reproduce it.
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/axios'
import { apiErrorMessage } from '../utils/apiError'
import { fieldLabel, fieldsForSection, SECTION_LABELS, TEMPLATE_TYPE_LABELS } from '../utils/printFields'
import { buildPreviewLines, PRINT_LINE_WIDTH } from '../utils/printTemplateLayout'
import type {
  PrintFieldAlignment,
  PrintFieldSection,
  PrintFieldSize,
  PrintTemplateDetail,
  PrintTemplateElement,
} from '../types'

const SECTIONS: PrintFieldSection[] = ['header', 'items', 'footer']
const ALIGNMENTS: PrintFieldAlignment[] = ['left', 'center', 'right', 'justify']
const FONT_SIZES: PrintFieldSize[] = ['small', 'normal', 'large', 'xlarge']

/** A working draft element — mirrors PrintTemplateElement but with a client-only id for brand-new rows not yet saved. */
type DraftElement = Omit<PrintTemplateElement, 'id'> & { id: string; isNew?: boolean }

function toDraft(elements: PrintTemplateElement[]): DraftElement[] {
  return elements.map((e) => ({ ...e }))
}

interface Props {
  template: PrintTemplateDetail
  brandId: string | null
  onClose: () => void
}

export function PrintTemplateEditor({ template, brandId, onClose }: Props) {
  const qc = useQueryClient()
  const params = brandId ? { brand_id: brandId } : {}
  const [elements, setElements] = useState<DraftElement[]>(() => toDraft(template.elements))
  const [selectedId, setSelectedId] = useState<string | null>(elements[0]?.id ?? null)
  const [dragId, setDragId] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: () =>
      api.put(
        `/print-templates/${template.id}/elements`,
        {
          elements: elements.map((e, i) => ({
            section: e.section,
            display_order: i,
            field_key: e.field_key,
            free_text_value: e.field_key === 'FREE_TEXT' ? e.free_text_value : null,
            font_size: e.font_size,
            alignment: e.alignment,
            is_bold: e.is_bold,
            is_italic: e.is_italic,
          })),
        },
        { params },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['print-templates', brandId] })
      setFormError(null)
      onClose()
    },
    onError: (e: unknown) => setFormError(apiErrorMessage(e, 'Failed to save template.')),
  })

  const selected = elements.find((e) => e.id === selectedId) ?? null

  const updateSelected = (patch: Partial<DraftElement>) => {
    if (!selected) return
    setElements((prev) => prev.map((e) => (e.id === selected.id ? { ...e, ...patch } : e)))
  }

  const addField = (section: PrintFieldSection, fieldKey: string) => {
    const id = `new-${crypto.randomUUID()}`
    const el: DraftElement = {
      id,
      section,
      display_order: elements.length,
      field_key: fieldKey,
      free_text_value: fieldKey === 'FREE_TEXT' ? '' : null,
      font_size: 'normal',
      alignment: 'left',
      is_bold: false,
      is_italic: false,
      isNew: true,
    }
    setElements((prev) => [...prev, el])
    setSelectedId(id)
  }

  const removeSelected = () => {
    if (!selected) return
    setElements((prev) => prev.filter((e) => e.id !== selected.id))
    setSelectedId(null)
  }

  // Native HTML5 drag-and-drop reorder — same technique as MenuBuilderPage's tab/button DnD.
  const handleDrop = (targetId: string) => {
    if (!dragId || dragId === targetId) return
    setElements((prev) => {
      const from = prev.findIndex((e) => e.id === dragId)
      const to = prev.findIndex((e) => e.id === targetId)
      if (from === -1 || to === -1) return prev
      const next = [...prev]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved)
      return next
    })
    setDragId(null)
  }

  const previewLines = buildPreviewLines(elements as unknown as PrintTemplateElement[], PRINT_LINE_WIDTH)

  return (
    <div className="fixed inset-0 z-40 bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h2 className="font-serif font-bold text-lg text-gray-900 dark:text-gray-100">{template.name}</h2>
            <p className="text-xs text-gray-500 dark:text-gray-400">{TEMPLATE_TYPE_LABELS[template.template_type]} template</p>
          </div>
          <div className="flex items-center gap-2">
            {formError && <p className="text-xs text-red-600 mr-2">{formError}</p>}
            <button onClick={onClose} className="text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700">
              Cancel
            </button>
            <button
              onClick={() => save.mutate()}
              disabled={save.isPending}
              className="px-3.5 py-2 bg-brand-600 text-white text-xs font-semibold rounded-lg hover:bg-brand-700 disabled:opacity-50"
            >
              {save.isPending ? 'Saving…' : 'Save template'}
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto grid grid-cols-1 md:grid-cols-3 gap-0">
          {/* Elements list */}
          <div className="md:col-span-1 border-r border-gray-200 dark:border-gray-700 p-4 overflow-auto">
            {SECTIONS.map((section) => (
              <div key={section} className="mb-4">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
                    {SECTION_LABELS[section]}
                  </span>
                  <AddFieldMenu
                    templateType={template.template_type}
                    section={section}
                    onAdd={(key) => addField(section, key)}
                  />
                </div>
                <div className="space-y-1">
                  {elements
                    .filter((e) => e.section === section)
                    .map((e) => (
                      <div
                        key={e.id}
                        draggable
                        onDragStart={() => setDragId(e.id)}
                        onDragOver={(ev) => ev.preventDefault()}
                        onDrop={() => handleDrop(e.id)}
                        onClick={() => setSelectedId(e.id)}
                        className={`flex items-center gap-2 px-2.5 py-2 rounded-lg text-sm cursor-pointer border ${
                          selectedId === e.id
                            ? 'bg-brand-50 dark:bg-brand-950/40 border-brand-400 dark:border-brand-600'
                            : 'border-transparent hover:bg-gray-50 dark:hover:bg-gray-700/40'
                        }`}
                      >
                        <span className="text-gray-300 dark:text-gray-600 cursor-grab select-none">⠿</span>
                        <span className="flex-1 truncate text-gray-900 dark:text-gray-100">
                          {fieldLabel(template.template_type, e.field_key)}
                        </span>
                      </div>
                    ))}
                  {elements.filter((e) => e.section === section).length === 0 && (
                    <p className="text-xs text-gray-300 dark:text-gray-600 italic px-2.5 py-1">No fields</p>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Inspector */}
          <div className="md:col-span-1 border-r border-gray-200 dark:border-gray-700 p-4 overflow-auto">
            {!selected ? (
              <p className="text-sm text-gray-400">Select a field to edit its style.</p>
            ) : (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Field</label>
                  <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                    {fieldLabel(template.template_type, selected.field_key)}
                  </p>
                </div>

                {selected.field_key === 'FREE_TEXT' && (
                  <div>
                    <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Text</label>
                    <input
                      value={selected.free_text_value ?? ''}
                      onChange={(e) => updateSelected({ free_text_value: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                    />
                  </div>
                )}

                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Alignment</label>
                  <div className="flex bg-gray-100 dark:bg-gray-900 rounded-lg p-1">
                    {ALIGNMENTS.map((a) => (
                      <button
                        key={a}
                        onClick={() => updateSelected({ alignment: a })}
                        className={`flex-1 px-2 py-1.5 rounded-md text-xs font-medium capitalize transition-colors ${
                          selected.alignment === a
                            ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
                            : 'text-gray-500 dark:text-gray-400'
                        }`}
                      >
                        {a}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Font size</label>
                  <select
                    value={selected.font_size}
                    onChange={(e) => updateSelected({ font_size: e.target.value as PrintFieldSize })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  >
                    {FONT_SIZES.map((s) => (
                      <option key={s} value={s} className="capitalize">{s}</option>
                    ))}
                  </select>
                </div>

                <div className="flex items-center gap-4">
                  <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                    <input
                      type="checkbox"
                      checked={selected.is_bold}
                      onChange={(e) => updateSelected({ is_bold: e.target.checked })}
                      className="rounded border-gray-300"
                    />
                    Bold
                  </label>
                  <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                    <input
                      type="checkbox"
                      checked={selected.is_italic}
                      onChange={(e) => updateSelected({ is_italic: e.target.checked })}
                      className="rounded border-gray-300"
                    />
                    Italic
                  </label>
                </div>

                <button
                  onClick={removeSelected}
                  className="text-xs font-medium text-red-600 hover:text-red-700"
                >
                  Remove field
                </button>
              </div>
            )}
          </div>

          {/* Live preview — same alignment/padding math as the printer's own output */}
          <div className="md:col-span-1 p-4 overflow-auto bg-gray-50 dark:bg-gray-900/40">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">
              Preview
            </p>
            <div className="bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-700 rounded-lg p-3 shadow-inner">
              <pre
                className="whitespace-pre font-mono text-[11px] leading-[1.5] text-gray-900 dark:text-gray-100"
                style={{ width: `${PRINT_LINE_WIDTH}ch` }}
              >
                {previewLines.map((line, i) => (
                  <div
                    key={i}
                    style={{
                      fontWeight: line.isBold ? 700 : 400,
                      fontStyle: line.isItalic ? 'italic' : 'normal',
                      fontSize: { small: '0.85em', normal: '1em', large: '1.25em', xlarge: '1.5em' }[line.fontSize],
                    }}
                  >
                    {line.text}
                  </div>
                ))}
              </pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function AddFieldMenu({
  templateType,
  section,
  onAdd,
}: {
  templateType: PrintTemplateDetail['template_type']
  section: PrintFieldSection
  onAdd: (fieldKey: string) => void
}) {
  const [open, setOpen] = useState(false)
  const fields = fieldsForSection(templateType, section)

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-xs font-semibold text-brand-600 hover:text-brand-700"
      >
        + Add field
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-1 w-56 max-h-64 overflow-auto bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-xl p-1">
          {fields.map((f) => (
            <button
              key={f.key}
              onClick={() => { onAdd(f.key); setOpen(false) }}
              className="w-full text-left px-2.5 py-2 rounded-md text-xs font-medium text-gray-900 dark:text-gray-100 hover:bg-brand-50 dark:hover:bg-brand-950/40 hover:text-brand-600"
            >
              {f.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
