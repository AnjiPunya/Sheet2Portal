import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchRecords } from '../api/portal'
import type { EntityConfig, RecordItem } from '../types/portal'
import type { RelatedFilter } from '../lib/portalView'
import { formatLabel } from '../lib/labels'
import { ApiRequestError } from '../api/client'
import { usePortalNav } from './portalContext'
import { SearchFilterBar } from './SearchFilterBar'
import { EntityCards } from './EntityCards'
import { EntityTable } from './EntityTable'
import { RecordDetailModal } from './RecordDetailModal'
import { KPICard } from './KPICard'
import { StatusBreakdownChart } from './StatusBreakdownChart'

const PAGE_SIZE = 24

function RelatedFilterChip({ filter, onClear }: { filter: RelatedFilter; onClear: () => void }) {
  const nav = usePortalNav()
  return (
    <div
      role="status"
      className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-indigo-200 bg-indigo-50/70 px-4 py-2.5"
    >
      <p className="flex min-w-0 items-center gap-2 text-sm text-indigo-900">
        <svg className="h-4 w-4 flex-shrink-0 text-indigo-500" viewBox="0 0 20 20" fill="currentColor" aria-hidden>
          <path
            fillRule="evenodd"
            d="M2.628 1.601C5.028 1.206 7.49 1 10 1s4.973.206 7.372.601a.75.75 0 01.628.74v2.288a2.25 2.25 0 01-.659 1.59l-4.682 4.683a2.25 2.25 0 00-.659 1.59v3.037c0 .684-.31 1.33-.844 1.757l-1.937 1.55A.75.75 0 018 18.25v-5.757a2.25 2.25 0 00-.659-1.591L2.659 6.22A2.25 2.25 0 012 4.629V2.34a.75.75 0 01.628-.74z"
            clipRule="evenodd"
          />
        </svg>
        <span className="truncate">
          Filtered to {nav.labelFor(filter.worksheet).toLowerCase()} <strong className="font-semibold">{filter.label}</strong>
        </span>
      </p>
      <button
        onClick={onClear}
        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-sm font-medium text-indigo-700 hover:bg-indigo-100"
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden>
          <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
        </svg>
        Clear filter
      </button>
    </div>
  )
}

export function EntityView({
  workbookId,
  entity,
  related,
  onClearRelated,
  embedded = false,
}: {
  workbookId: string
  entity: EntityConfig
  /** Restrict the list to records related to one parent record ("View all"). */
  related?: RelatedFilter
  onClearRelated?: () => void
  /** Set when embedded in a parent (e.g. Dashboard) that already shows this
   * entity's KPI cards -- suppresses the KPI strip to avoid duplicating them. */
  embedded?: boolean
}) {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<RecordItem | null>(null)

  const query = useQuery({
    queryKey: ['records', workbookId, entity.worksheet, related?.worksheet, related?.recordId, search, status, page],
    queryFn: () =>
      fetchRecords(workbookId, entity.worksheet, {
        search: search || undefined,
        status: status || undefined,
        related,
        page,
        pageSize: PAGE_SIZE,
      }),
    placeholderData: (previous) => previous,
  })

  const totalPages = query.data ? Math.max(1, Math.ceil(query.data.total / PAGE_SIZE)) : 1
  // Workbook-wide KPIs/chart would contradict a filtered list, so they're
  // hidden while a related filter is active.
  const showKpis = !embedded && !related && entity.kpis.length > 0
  const hasChart = !related && entity.status_breakdown.length >= 2
  const loadError = query.error instanceof ApiRequestError ? query.error : null

  return (
    <div className="space-y-5">
      {showKpis || hasChart ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {showKpis && (
            <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 sm:grid-cols-3 lg:col-span-2">
              {entity.kpis.map((kpi) => (
                <KPICard key={kpi.key} kpi={kpi} />
              ))}
            </div>
          )}
          {hasChart && (
            <div className={`panel p-5 ${showKpis ? '' : 'lg:col-span-3'}`}>
              <p className="section-label mb-4">{formatLabel(entity.status_column ?? 'Status')} breakdown</p>
              <StatusBreakdownChart items={entity.status_breakdown} />
            </div>
          )}
        </div>
      ) : null}

      {related && onClearRelated && <RelatedFilterChip filter={related} onClear={onClearRelated} />}

      <SearchFilterBar
        entity={entity}
        search={search}
        status={status}
        onSearchChange={(value) => {
          setSearch(value)
          setPage(1)
        }}
        onStatusChange={(value) => {
          setStatus(value)
          setPage(1)
        }}
        total={query.data?.total ?? (related ? undefined : entity.row_count)}
      />

      {query.isLoading && (
        <div className="panel animate-pulse space-y-3 p-5">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-4 rounded bg-slate-100" />
          ))}
        </div>
      )}

      {loadError && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          Couldn&apos;t load records: {loadError.message}
        </div>
      )}

      {query.data &&
        (entity.layout === 'cards' ? (
          <EntityCards entity={entity} records={query.data.records} onSelect={setSelected} />
        ) : (
          <EntityTable entity={entity} records={query.data.records} onSelect={setSelected} />
        ))}

      {totalPages > 1 && (
        <div className="flex items-center justify-between gap-3 text-sm">
          <span className="text-slate-500">
            Page <span className="font-medium text-slate-700">{page}</span> of {totalPages}
          </span>
          <div className="flex gap-2">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="btn-secondary">
              ← Previous
            </button>
            <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="btn-secondary">
              Next →
            </button>
          </div>
        </div>
      )}

      {selected && (
        <RecordDetailModal
          workbookId={workbookId}
          worksheet={entity.worksheet}
          record={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}
