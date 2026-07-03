/**
 * Extract a human-readable message from an Axios error response.
 *
 * FastAPI returns `detail` as a string for HTTPException errors and as an
 * array of {loc, msg, type} objects for 422 validation errors — handle both
 * so mutation onError handlers can show the real reason instead of a generic
 * "Failed to …" message.
 */

interface ValidationItem {
  loc?: (string | number)[]
  msg?: string
}

/** Return the backend's error detail, or the given fallback when unavailable. */
export function apiErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail.length > 0) return detail
  if (Array.isArray(detail)) {
    // 422 validation errors: show "field: message" for each offending field
    const parts = (detail as ValidationItem[])
      .map((d) => {
        const field = d.loc?.slice(1).join('.') ?? ''
        return field ? `${field}: ${d.msg ?? 'invalid'}` : d.msg ?? ''
      })
      .filter(Boolean)
    if (parts.length > 0) return parts.join('; ')
  }
  return fallback
}
