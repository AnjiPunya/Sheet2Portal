import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchRecords } from '../api/portal'
import type { EntityConfig, RecordItem } from '../types/portal'
import { SearchFilterBar } from './SearchFilterBar'
import { EntityCards } from './EntityCards'
import { EntityTable } from './EntityTable'
import { RecordDetailModal } from './RecordDetailModal'
import { KPICard } from './KPICard'
import { StatusBreakdownChart } from './StatusBreakdownChart'

const PAGE_SIZE = 24

export function EntityView({
  workbookId,
  entity,
  onNavigateEntity,
  titleColumnByWorksheet,
  embedded = false,
}: {
  workbookId: string
  entity: EntityConfig
  onNavigateEntity: (worksheet: string) => void
  titleColumnByWorksheet: Record<string, string | null>
  /** Set when embedded in a parent (e.g. Dashboard) that already shows this
   * entity's KPI cards -- suppresses the KPI strip to avoid duplicating them. */
  embedded?: boolean
}) {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<RecordItem | null>(null)

  const query = useQuery({
    queryKey: ['records', workbookId, entity.worksheet, search, status, page],
    queryFn: () =>
      fetchRecords(workbookId, entity.worksheet, {
        search: search || undefined,
        status: status || undefined,
        page,
        pageSize: PAGE_SIZE,
      }),
  })

  const totalPages = query.data ? Math.max(1, Math.ceil(query.data.total / PAGE_SIZE)) : 1

  const hasChart = entity.status_breakdown.length >= 2

  return (
    <div className="space-y-4">
      {(!embedded && entity.kpis.length > 0) || hasChart ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {!embedded && entity.kpis.length > 0 && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:col-span-2 lg:grid-cols-3">
              {entity.kpis.map((kpi) => (
                <KPICard key={kpi.key} kpi={kpi} />
              ))}
            </div>
          )}
          {hasChart && (
            <div
              className={`rounded-xl border border-slate-200 bg-white p-4 ${!embedded && entity.kpis.length > 0 ? '' : 'lg:col-span-3'}`}
            >
              <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
                {entity.status_column ?? 'Status'} Breakdown
              </p>
              <StatusBreakdownChart items={entity.status_breakdown} />
            </div>
          )}
        </div>
      ) : null}

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
        total={query.data?.total ?? entity.row_count}
      />

      {query.isLoading && <p className="text-sm text-slate-400">Loading…</p>}

      {query.data &&
        (entity.layout === 'cards' ? (
          <EntityCards entity={entity} records={query.data.records} onSelect={setSelected} />
        ) : (
          <EntityTable entity={entity} records={query.data.records} onSelect={setSelected} />
        ))}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="rounded border border-slate-200 px-3 py-1 text-slate-600 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-slate-500">
            Page {page} of {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className="rounded border border-slate-200 px-3 py-1 text-slate-600 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}

      {selected && (
        <RecordDetailModal
          workbookId={workbookId}
          worksheet={entity.worksheet}
          record={selected}
          titleColumnByWorksheet={titleColumnByWorksheet}
          onClose={() => setSelected(null)}
          onNavigateEntity={onNavigateEntity}
        />
      )}
    </div>
  )
}
