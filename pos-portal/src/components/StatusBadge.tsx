/**
 * Status pill following the Portal Design Guide (§03 ".spill" / §01 semantic
 * colours). Renders a 6px colour dot + label with a semantic background driven
 * by the `--zr-*` tokens. Optionally clickable to toggle state inline (Stage 20).
 */

/** The four semantic families defined in the design guide. */
type PillFamily = 'live' | 'pending' | 'draft' | 'void'

/**
 * Maps every status string used across the portal onto one of the four
 * guide families. Anything unmapped falls back to the neutral "draft" family.
 */
const FAMILY: Record<string, PillFamily> = {
  // green — live / published / paid
  active: 'live',
  paid: 'live',
  published: 'live',
  live: 'live',
  // amber — scheduled / pending
  open: 'pending',
  pending: 'pending',
  scheduled: 'pending',
  suspended: 'pending',
  partial: 'pending',
  // grey — draft / unpublished / inactive
  draft: 'draft',
  disabled: 'draft',
  cancelled: 'draft',
  inactive: 'draft',
  unpublished: 'draft',
  // red — void / refund / error / expired
  expired: 'void',
  void: 'void',
  refund: 'void',
  refunded: 'void',
  error: 'void',
  failed: 'void',
}

interface Props {
  status: string
  /** When provided, the badge renders as a button (e.g. click to activate/deactivate). */
  onClick?: () => void
  disabled?: boolean
  title?: string
}

export function StatusBadge({ status, onClick, disabled, title }: Props) {
  // Resolve the semantic family from the raw status string (case-insensitive).
  const family = FAMILY[status.toLowerCase()] ?? 'draft'
  const pill = `zr-pill zr-pill--${family} capitalize`

  if (!onClick) {
    return <span className={pill}>{status}</span>
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      // Subtle ring on hover signals the pill is interactive (toggle state).
      className={`${pill} hover:ring-2 hover:ring-offset-1 hover:ring-current transition-shadow disabled:opacity-50 disabled:hover:ring-0`}
    >
      {status}
    </button>
  )
}
