/** Coloured pill badge for entity status values. Optionally clickable to toggle state inline (Stage 20). */

interface Props {
  status: string
  /** When provided, the badge renders as a button (e.g. click to activate/deactivate). */
  onClick?: () => void
  disabled?: boolean
  title?: string
}

const COLOURS: Record<string, string> = {
  active: 'bg-green-100 text-green-700',
  expired: 'bg-red-100 text-red-700',
  disabled: 'bg-gray-100 text-gray-600',
  open: 'bg-blue-100 text-blue-700',
  paid: 'bg-green-100 text-green-700',
  cancelled: 'bg-gray-100 text-gray-500',
  suspended: 'bg-amber-100 text-amber-700',
}

export function StatusBadge({ status, onClick, disabled, title }: Props) {
  const cls = COLOURS[status] ?? 'bg-gray-100 text-gray-600'
  const pill = `inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${cls}`

  if (!onClick) {
    return <span className={pill}>{status}</span>
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`${pill} hover:ring-2 hover:ring-offset-1 hover:ring-current transition-shadow disabled:opacity-50 disabled:hover:ring-0`}
    >
      {status}
    </button>
  )
}
