/** Displays a human-readable ref ID (e.g. GRO-000001) or truncated UUID with click-to-copy. */

import { useState } from 'react'

interface Props {
  id: string
  /** Human-readable reference like GRO-000001. When provided, displayed instead of the truncated UUID. */
  ref?: string
}

export function EntityIdChip({ id, ref }: Props) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(id)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <button
      onClick={handleCopy}
      title={`${ref ? ref + ' · ' : ''}${id}`}
      className="font-mono text-xs bg-gray-100 hover:bg-gray-200 text-gray-600 px-2 py-0.5 rounded cursor-pointer transition-colors"
    >
      {copied ? '✓ copied' : (ref ?? id.slice(0, 8) + '…')}
    </button>
  )
}
