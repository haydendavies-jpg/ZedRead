/** A colour swatch button that opens a popover: curated palette + native colour picker. */

import { useEffect, useRef, useState } from 'react'
import { MENU_STUDIO_PALETTE } from '../utils/menuStudio'

interface ColorSwatchPickerProps {
  value: string
  onChange: (color: string) => void
  title?: string
}

export function ColorSwatchPicker({ value, onChange, title }: ColorSwatchPickerProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDocClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [open])

  return (
    <div className="relative inline-block" ref={ref}>
      <button
        type="button"
        title={title ?? 'Colour'}
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o) }}
        className="w-6 h-6 rounded-md border border-black/10 dark:border-white/20 shrink-0"
        style={{ background: value }}
      />
      {open && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute z-40 top-full left-0 mt-2 w-56 p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg"
        >
          <div className="text-[10.5px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">
            Colour
          </div>
          <div className="flex flex-wrap gap-2">
            {MENU_STUDIO_PALETTE.map((color) => (
              <button
                key={color}
                type="button"
                onClick={() => { onChange(color); setOpen(false) }}
                className={`w-7 h-7 rounded-lg border-2 ${value === color ? 'border-gray-900 dark:border-gray-100' : 'border-transparent'}`}
                style={{ background: color }}
              />
            ))}
          </div>
          <label className="flex items-center gap-2 mt-3 text-xs font-medium text-gray-500 dark:text-gray-400 cursor-pointer">
            <input
              type="color"
              value={value}
              onChange={(e) => onChange(e.target.value)}
              className="w-7 h-7 border-none bg-transparent cursor-pointer p-0"
            />
            Custom…
          </label>
        </div>
      )}
    </div>
  )
}
