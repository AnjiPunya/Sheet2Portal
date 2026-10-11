import type { StatusBreakdownItem } from '../types/portal'

// Fixed status palette (never themed/cycled) -- risk items get the warning
// step, everything else gets the good step. Always paired with the direct
// text label beside each bar, never color alone.
const GOOD = '#0ca30c'
const WARNING = '#fab219'

export function StatusBreakdownChart({ items, max = 6 }: { items: StatusBreakdownItem[]; max?: number }) {
  if (items.length < 2) return null

  const shown = items.slice(0, max)
  const maxCount = Math.max(...shown.map((item) => item.count), 1)

  return (
    <div className="flex flex-col gap-2.5">
      {shown.map((item) => (
        <div key={item.value} className="flex items-center gap-3">
          <span className="w-28 flex-shrink-0 truncate text-sm text-slate-600 sm:w-36" title={item.value}>
            {item.value}
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${Math.max((item.count / maxCount) * 100, 4)}%`,
                backgroundColor: item.is_risk ? WARNING : GOOD,
              }}
            />
          </div>
          <span className="w-8 flex-shrink-0 text-right text-sm font-medium text-slate-800 tabular-nums">{item.count}</span>
        </div>
      ))}
    </div>
  )
}
