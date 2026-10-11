import { categoryColors, TONES } from '../../lib/chartFormat'

/** Horizontal bars for a status/category breakdown. Each row carries its own
 * colour key + icon + label (the legend sits on the row), so statuses are
 * never told apart by colour alone. */
export function CategoryBars({ items, max = 8 }: { items: { label: string; value: number }[]; max?: number }) {
  const rows = items.slice(0, max)
  const colors = categoryColors(rows.map((r) => r.label))
  const top = Math.max(...rows.map((r) => r.value), 1)
  return (
    <ul className="space-y-2.5">
      {rows.map((row, i) => {
        const { color, tone } = colors[i]
        return (
          <li key={row.label} className="grid grid-cols-[minmax(0,9rem)_1fr_2rem] items-center gap-3 text-sm">
            <span className="flex min-w-0 items-center gap-1.5 text-slate-700" title={tone ? `${row.label} (${TONES[tone].meaning})` : row.label}>
              <span
                className="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded text-[10px] font-bold leading-none text-white"
                style={{ backgroundColor: color }}
                aria-hidden
              >
                {tone ? TONES[tone].icon : ''}
              </span>
              <span className="truncate">{row.label}</span>
            </span>
            <div className="h-2.5 rounded-r-[4px] transition-[width] duration-500" style={{ width: `${Math.max((row.value / top) * 100, 2)}%`, backgroundColor: color }} />
            <span className="text-right font-medium text-slate-800 tabular-nums">{row.value}</span>
          </li>
        )
      })}
    </ul>
  )
}
