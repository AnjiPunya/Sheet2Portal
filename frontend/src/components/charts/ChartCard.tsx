import { useState, type ReactNode } from 'react'

export interface TableView {
  columns: string[]
  rows: (string | number)[][]
}

/** Chart frame: title, optional note, and a table view so every value is
 * reachable without hovering (and for screen readers). */
export function ChartCard({
  title,
  note,
  legend,
  table,
  children,
}: {
  title: string
  note?: string | null
  legend?: ReactNode
  table: TableView
  children: ReactNode
}) {
  const [showTable, setShowTable] = useState(false)
  return (
    <figure className="panel flex flex-col gap-4 p-5">
      <figcaption className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-800">{title}</p>
          {note && <p className="mt-0.5 text-xs text-slate-500">{note}</p>}
        </div>
        <button
          onClick={() => setShowTable((v) => !v)}
          aria-pressed={showTable}
          className="shrink-0 rounded-md px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-700"
        >
          {showTable ? 'Chart' : 'Table'}
        </button>
      </figcaption>
      {showTable ? (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
                {table.columns.map((c, i) => (
                  <th key={c} className={`py-1.5 pr-4 font-medium ${i > 0 ? 'text-right' : ''}`}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {table.rows.map((row, r) => (
                <tr key={r} className="border-b border-slate-100 last:border-0">
                  {row.map((cell, i) => (
                    <td key={i} className={`py-1.5 pr-4 ${i > 0 ? 'text-right text-slate-800' : 'text-slate-700'}`}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <>
          {children}
          {legend}
        </>
      )}
    </figure>
  )
}

/** Legend entries: a swatch beside text in ink colors (text never wears the data color). */
export function Legend({ items }: { items: { label: string; color: string; detail?: string }[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-slate-600">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: item.color }} aria-hidden />
          <span>{item.label}</span>
          {item.detail && <span className="font-medium text-slate-800 tabular-nums">{item.detail}</span>}
        </li>
      ))}
    </ul>
  )
}

/** One floating tooltip per chart; values lead, labels follow. */
export interface TooltipState {
  x: number
  y: number
  title: string
  rows: { label: string; value: string; color?: string }[]
}

export function ChartTooltip({ tip }: { tip: TooltipState | null }) {
  if (!tip) return null
  return (
    <div
      role="tooltip"
      className="pointer-events-none absolute z-10 min-w-36 -translate-x-1/2 -translate-y-full rounded-lg bg-slate-900 px-3 py-2 text-xs text-white shadow-lg"
      style={{ left: tip.x, top: tip.y - 8 }}
    >
      <p className="mb-1 text-slate-300">{tip.title}</p>
      {tip.rows.map((row) => (
        <p key={row.label} className="flex items-center justify-between gap-3">
          <span className="flex items-center gap-1.5 text-slate-300">
            {row.color && <span className="h-0.5 w-3 rounded" style={{ backgroundColor: row.color }} aria-hidden />}
            {row.label}
          </span>
          <span className="font-semibold tabular-nums">{row.value}</span>
        </p>
      ))}
    </div>
  )
}
