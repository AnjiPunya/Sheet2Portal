import type { ColumnProfile, EntityConfig, RecordItem } from '../types/portal'
import { StatusBadge } from './StatusBadge'
import { formatCellValue } from '../lib/format'
import { formatLabel } from '../lib/labels'
import { isLowStock } from '../lib/lowStock'

const DETAIL_ROLE_PRIORITY = [
  'person',
  'foreign_key',
  'due_date',
  'date',
  'budget_amount',
  'actual_amount',
  'amount',
  'quantity',
  'threshold',
]

function pickDetailColumns(entity: EntityConfig, max = 4): ColumnProfile[] {
  const excluded = new Set([entity.title_column, entity.status_column].filter(Boolean))
  const strategy = entity.low_stock_strategy
  // When a card can show a "Low stock" badge, make sure the numbers that
  // explain it (quantity/threshold, or the opening+in-out flow) are
  // actually visible rather than being crowded out by lower-priority fields.
  const lowStockColumns = strategy
    ? [strategy.quantity_column, strategy.opening_column, strategy.inbound_column, strategy.outbound_column, strategy.threshold_column].filter(
        (c): c is string => !!c,
      )
    : []

  const eligible = entity.columns.filter(
    (c) => !excluded.has(c.name) && (DETAIL_ROLE_PRIORITY.includes(c.role) || lowStockColumns.includes(c.name)),
  )
  eligible.sort((a, b) => {
    const aPriority = lowStockColumns.includes(a.name) ? -1 : DETAIL_ROLE_PRIORITY.indexOf(a.role)
    const bPriority = lowStockColumns.includes(b.name) ? -1 : DETAIL_ROLE_PRIORITY.indexOf(b.role)
    return aPriority - bPriority
  })
  return eligible.slice(0, lowStockColumns.length > 0 ? Math.max(max, lowStockColumns.length + 1) : max)
}

export function EntityCards({
  entity,
  records,
  onSelect,
}: {
  entity: EntityConfig
  records: RecordItem[]
  onSelect: (record: RecordItem) => void
}) {
  const detailColumns = pickDetailColumns(entity)
  const riskByStatus = new Map(entity.status_breakdown.map((s) => [s.value, s.is_risk]))

  if (records.length === 0) {
    return (
      <div className="panel px-6 py-12 text-center">
        <p className="text-sm font-medium text-slate-700">No records match the current filters</p>
        <p className="mt-1 text-sm text-slate-500">Try a different search or clear a filter.</p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {records.map((record) => {
        const title = entity.title_column ? formatCellValue(record.data[entity.title_column]) : null
        const statusValue = entity.status_column ? formatCellValue(record.data[entity.status_column]) : null
        const lowStock = isLowStock(record.data, entity.low_stock_strategy)
        return (
          <button
            key={record.id}
            onClick={() => onSelect(record)}
            className={`flex flex-col gap-3 rounded-xl border p-4 text-left shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition hover:-translate-y-px hover:border-slate-300 hover:shadow-md
              ${lowStock ? 'border-red-200 bg-red-50/60' : 'border-slate-200/80 bg-white'}`}
          >
            <div className="flex items-start justify-between gap-2">
              <span className="font-semibold leading-snug text-slate-900">{title || 'Untitled'}</span>
              <div className="flex flex-shrink-0 items-center gap-1.5">
                {lowStock && (
                  <span className="rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-medium text-red-700">
                    Low stock
                  </span>
                )}
                {statusValue && <StatusBadge value={statusValue} isRisk={riskByStatus.get(statusValue)} />}
              </div>
            </div>
            <dl className="flex flex-col gap-1.5 border-t border-slate-100 pt-3 text-sm">
              {detailColumns.map((col) => {
                const value = formatCellValue(record.data[col.name])
                if (!value) return null
                return (
                  <div key={col.name} className="flex justify-between gap-3">
                    <dt className="text-slate-500">{formatLabel(col.name)}</dt>
                    <dd className="text-right font-medium text-slate-800 tabular-nums">{value}</dd>
                  </div>
                )
              })}
            </dl>
          </button>
        )
      })}
    </div>
  )
}
