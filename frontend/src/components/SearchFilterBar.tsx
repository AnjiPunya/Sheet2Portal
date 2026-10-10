import type { EntityConfig } from '../types/portal'

interface Props {
  entity: EntityConfig
  search: string
  status: string
  onSearchChange: (value: string) => void
  onStatusChange: (value: string) => void
  total: number
}

export function SearchFilterBar({ entity, search, status, onSearchChange, onStatusChange, total }: Props) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-1 flex-wrap gap-2">
        <input
          type="text"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder={`Search ${entity.label.toLowerCase()}...`}
          className="w-full max-w-xs rounded-lg border border-slate-200 px-3 py-1.5 text-sm focus:border-indigo-400 focus:outline-none"
        />
        {entity.status_column && entity.status_breakdown.length > 0 && (
          <select
            value={status}
            onChange={(e) => onStatusChange(e.target.value)}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm focus:border-indigo-400 focus:outline-none"
          >
            <option value="">All {entity.status_column}</option>
            {entity.status_breakdown.map((item) => (
              <option key={item.value} value={item.value}>
                {item.value} ({item.count})
              </option>
            ))}
          </select>
        )}
      </div>
      <span className="whitespace-nowrap text-sm text-slate-400">
        {total} {total === 1 ? entity.singular_label.toLowerCase() : entity.label.toLowerCase()}
      </span>
    </div>
  )
}
