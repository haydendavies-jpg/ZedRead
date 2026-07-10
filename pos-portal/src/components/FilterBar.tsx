/** Shared search + filter dropdown bar for catalog table pages (Stage 20). Filtering is client-side. */

export interface FilterConfig {
  label: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
}

interface Props {
  search: string
  onSearchChange: (value: string) => void
  searchPlaceholder?: string
  filters?: FilterConfig[]
  hasFilters: boolean
  onClear: () => void
  resultCount: number
  totalCount: number
}

export function FilterBar({
  search,
  onSearchChange,
  searchPlaceholder = 'Search…',
  filters = [],
  hasFilters,
  onClear,
  resultCount,
  totalCount,
}: Props) {
  return (
    <div className="flex flex-wrap items-end gap-3 mb-4">
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-500">Search</label>
        <input
          type="text"
          placeholder={searchPlaceholder}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm w-56 focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
      </div>
      {filters.map((f) => (
        <div key={f.label} className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">{f.label}</label>
          <select
            value={f.value}
            onChange={(e) => f.onChange(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            {f.options.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      ))}
      {hasFilters && (
        <button onClick={onClear} className="text-xs text-gray-400 hover:text-gray-600 pb-2">
          Clear filters
        </button>
      )}
      <span className="text-xs text-gray-400 ml-auto pb-2">{resultCount} of {totalCount}</span>
    </div>
  )
}
