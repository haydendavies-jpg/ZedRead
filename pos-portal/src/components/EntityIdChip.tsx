/** Displays a truncated UUID with a click-to-copy behaviour. */

import { useState } from 'react'

interface Props {
  id: string
}

export function EntityIdChip({ id }: Props) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(id)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <button
      onClick={handleCopy}
      title={id}
      className="font-mono text-xs bg-gray-100 hover:bg-gray-200 text-gray-600 px-2 py-0.5 rounded cursor-pointer transition-colors"
    >
      {copied ? '✓ copied' : id.slice(0, 8) + '…'}
    </button>
  )
}
