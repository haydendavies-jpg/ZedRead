/** Simple modal overlay with close-on-backdrop-click. */

import React, { useEffect } from 'react'

interface Props {
  title: string
  onClose: () => void
  children: React.ReactNode
  /** When true, uses a wider max-width (4xl) and makes the inner content scrollable. */
  wide?: boolean
}

export function Modal({ title, onClose, children, wide = false }: Props) {
  // Close on Escape key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 overflow-y-auto py-6"
      onClick={onClose}
    >
      <div
        className={`bg-white rounded-xl shadow-xl w-full mx-4 p-6 ${wide ? 'max-w-4xl' : 'max-w-md'}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-gray-900">{title}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
