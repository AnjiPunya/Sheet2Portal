import type { WorksheetOut } from '../types/workbook'
import { TypeBadge } from './TypeBadge'

export function SampleTable({ sheet }: { sheet: WorksheetOut }) {
  if (sheet.columns.length === 0) {
    return <p className="py-6 text-sm text-slate-400">No columns detected in this sheet.</p>
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr>
            {sheet.columns.map((col) => (
              <th key={col.position} className="whitespace-nowrap px-3 py-2 text-left font-semibold text-slate-600">
                <div className="flex flex-col gap-1">
                  <span>{col.name}</span>
                  <TypeBadge type={col.inferred_type} confidence={col.confidence} />
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {sheet.sample_rows.map((row, i) => (
            <tr key={i} className="hover:bg-slate-50">
              {sheet.columns.map((col) => (
                <td key={col.position} className="whitespace-nowrap px-3 py-2 text-slate-700">
                  {row[col.name] === null || row[col.name] === undefined ? (
                    <span className="text-slate-300">—</span>
                  ) : (
                    String(row[col.name])
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
