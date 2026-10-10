import type { ColumnProfile, EntityConfig, RecordItem } from '../types/portal'
import { StatusBadge } from './StatusBadge'
import { formatCellValue } from '../lib/format'
import { isLowStock } from '../lib/lowStock'

const MAX_COLUMNS = 7

function pickDisplayColumns(entity: EntityConfig): ColumnProfile[] {
  const lowStockColumns = new Set(
    entity.low_stock_strategy
      ? [
          entity.low_stock_strategy.quantity_column,
          entity.low_stock_strategy.threshold_column,
          entity.low_stock_strategy.opening_column,
        ].filter((c): c is string => !!c)
      : [],
  )
  const priority = (name: string) => {
    if (name === entity.identifier_column) return 0
    if (name === entity.title_column) return 1
    if (name === entity.status_column) return 2
    if (lowStockColumns.has(name)) return 3
    return 4
  }
  return [...entity.columns]
    .sort((a, b) => priority(a.name) - priority(b.name))
    .slice(0, MAX_COLUMNS)
    .sort((a, b) => a.position - b.position)
}

export function EntityTable({
  entity,
  records,
  onSelect,
}: {
  entity: EntityConfig
  records: RecordItem[]
  onSelect: (record: RecordItem) => void
}) {
  const columns = pickDisplayColumns(entity)
  const riskByStatus = new Map(entity.status_breakdown.map((s) => [s.value, s.is_risk]))

  if (records.length === 0) {
    return <p className="py-8 text-center text-sm text-slate-400">No records match the current filters.</p>
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr>
            {columns.map((col) => (
              <th key={col.name} className="whitespace-nowrap px-3 py-2 text-left font-semibold text-slate-600">
                {col.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {records.map((record) => {
            const lowStock = isLowStock(record.data, entity.low_stock_strategy)
            return (
              <tr
                key={record.id}
                onClick={() => onSelect(record)}
                className={`cursor-pointer ${lowStock ? 'bg-red-50/70 hover:bg-red-50' : 'hover:bg-slate-50'}`}
              >
                {columns.map((col) => {
                  const value = record.data[col.name]
                  if (col.name === entity.status_column && value) {
                    const strValue = formatCellValue(value)
                    return (
                      <td key={col.name} className="whitespace-nowrap px-3 py-2">
                        <StatusBadge value={strValue} isRisk={riskByStatus.get(strValue)} />
                      </td>
                    )
                  }
                  const formatted = formatCellValue(value)
                  const isQuantityCell =
                    lowStock &&
                    (col.name === entity.low_stock_strategy?.quantity_column ||
                      col.name === entity.low_stock_strategy?.opening_column)
                  return (
                    <td
                      key={col.name}
                      className={`whitespace-nowrap px-3 py-2 ${isQuantityCell ? 'font-semibold text-red-700' : 'text-slate-700'}`}
                    >
                      <span className="flex items-center gap-1.5">
                        {formatted || <span className="text-slate-300">—</span>}
                        {lowStock && col.name === entity.title_column && (
                          <span className="rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-medium text-red-700">
                            Low stock
                          </span>
                        )}
                      </span>
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
