import type { EntityConfig } from '../types/portal'
import { formatLabel } from '../lib/labels'

interface Props {
  entity: EntityConfig
  search: string
  status: string
  onSearchChange: (value: string) => void
  onStatusChange: (value: string) => void
  /** Matching record count; undefined while a filtered count is loading. */
  total: number | undefined
}

export function SearchFilterBar({ entity, search, status, onSearchChange, onStatusChange, total }: Props) {
  const label = formatLabel(entity.label)
  const singular = formatLabel(entity.singular_label)
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-1 flex-col gap-2 min-[480px]:flex-row">
        <label className="relative w-full min-[480px]:max-w-xs">
          <span className="sr-only">Search {label}</span>
          <svg
            className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-slate-400"
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden
          >
            <path
              fillRule="evenodd"
              d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z"
              clipRule="evenodd"
            />
          </svg>
          <input
            type="search"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={`Search ${label.toLowerCase()}…`}
            className="input w-full pl-9"
          />
        </label>
        {entity.status_column && entity.status_breakdown.length > 0 && (
          <label>
            <span className="sr-only">Filter by {formatLabel(entity.status_column)}</span>
            <select value={status} onChange={(e) => onStatusChange(e.target.value)} className="input w-full min-[480px]:w-auto">
              <option value="">All {formatLabel(entity.status_column).toLowerCase()} values</option>
              {entity.status_breakdown.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.value} ({item.count})
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <span className="text-sm whitespace-nowrap text-slate-500 tabular-nums">
        {total === undefined ? '…' : `${total} ${total === 1 ? singular.toLowerCase() : label.toLowerCase()}`}
      </span>
    </div>
  )
}
