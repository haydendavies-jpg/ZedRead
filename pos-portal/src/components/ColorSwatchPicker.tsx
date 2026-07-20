/** A colour swatch button that opens a popover: curated palette + native colour picker. */

import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { MENU_STUDIO_PALETTE } from '../utils/menuStudio'

interface ColorSwatchPickerProps {
  value: string
  onChange: (color: string) => void
  title?: string
  /**
   * 'swatch' (default) previews `value` as the trigger's own fill — reads fine on a neutral
   * surface (e.g. Categories' card row). 'icon' renders a small neutral edit-pencil button
   * instead, for triggers that already sit on a surface filled with `value` itself (e.g. a
   * Menu Builder tab tile) — there, a same-coloured swatch reads as a redundant chip that
   * blends into its own background rather than as a colour preview.
   */
  trigger?: 'swatch' | 'icon'
}

const POPOVER_WIDTH = 224 // w-56

export function ColorSwatchPicker({ value, onChange, title, trigger = 'swatch' }: ColorSwatchPickerProps) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState({ top: 0, left: 0 })
  const btnRef = useRef<HTMLButtonElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node
      if (popoverRef.current?.contains(target) || btnRef.current?.contains(target)) return
      setOpen(false)
    }
    // The popover's position is computed once, on open, from the trigger button's
    // viewport rect (see handleToggle) — it isn't re-measured on scroll, so close it
    // instead of letting it drift out of alignment with the button that opened it.
    const onScroll = () => setOpen(false)
    document.addEventListener('mousedown', onDocClick)
    window.addEventListener('scroll', onScroll, true)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      window.removeEventListener('scroll', onScroll, true)
    }
  }, [open])

  // Renders the popover into document.body at a viewport-fixed position (rather than
  // `absolute` inside this button's own DOM position) so it can never be clipped by an
  // ancestor's `overflow: auto/hidden` — e.g. the Menu Builder rail, which is exactly
  // narrow + scrollable enough to have cut the old absolutely-positioned popover off.
  const handleToggle = () => {
    if (!open) {
      const rect = btnRef.current?.getBoundingClientRect()
      if (rect) {
        const left = Math.min(rect.left, window.innerWidth - POPOVER_WIDTH - 8)
        setPos({ top: rect.bottom + 8, left: Math.max(8, left) })
      }
    }
    setOpen((o) => !o)
  }

  return (
    <>
      {trigger === 'icon' ? (
        <button
          ref={btnRef}
          type="button"
          title={title ?? 'Colour'}
          onClick={(e) => { e.stopPropagation(); handleToggle() }}
          className="w-6 h-6 rounded-md bg-white/90 hover:bg-white text-gray-700 shadow-sm flex items-center justify-center text-[11px] shrink-0"
        >
          ✎
        </button>
      ) : (
        <button
          ref={btnRef}
          type="button"
          title={title ?? 'Colour'}
          onClick={(e) => { e.stopPropagation(); handleToggle() }}
          className="w-6 h-6 rounded-md border border-black/20 dark:border-white/30 shrink-0"
          style={{ background: value }}
        />
      )}
      {open &&
        createPortal(
          <div
            ref={popoverRef}
            onClick={(e) => e.stopPropagation()}
            style={{ top: pos.top, left: pos.left, width: POPOVER_WIDTH }}
            className="fixed z-[200] p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg"
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
                  className="relative w-7 h-7 rounded-lg"
                  style={{ background: color }}
                >
                  {/* A border can't be relied on to show up against an arbitrary swatch
                      colour (a dark border on an already-dark swatch is nearly invisible) —
                      a small white-on-dark badge stays legible against every palette colour. */}
                  {value === color && (
                    <span className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-white text-gray-900 text-[9px] font-bold flex items-center justify-center shadow ring-1 ring-black/15">
                      ✓
                    </span>
                  )}
                </button>
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
          </div>,
          document.body,
        )}
    </>
  )
}
