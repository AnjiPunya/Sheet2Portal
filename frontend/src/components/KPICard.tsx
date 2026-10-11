import type { KPIDefinition } from '../types/portal'
import { formatKpiValue } from '../lib/format'
import { formatLabel } from '../lib/labels'

const SEVERITY_STYLES: Record<string, { card: string; label: string; value: string; dot: string }> = {
  critical: { card: 'border-red-200 bg-red-50/70', label: 'text-red-700', value: 'text-red-700', dot: 'bg-red-500' },
  warning: { card: 'border-amber-200 bg-amber-50/70', label: 'text-amber-800', value: 'text-amber-700', dot: 'bg-amber-500' },
}

export function KPICard({ kpi, onClick }: { kpi: KPIDefinition; onClick?: () => void }) {
  const severity = kpi.severity ? SEVERITY_STYLES[kpi.severity] : null
  const className = `group flex h-full w-full flex-col gap-2 rounded-xl border p-4 text-left shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition
    ${onClick ? 'cursor-pointer hover:-translate-y-px hover:shadow-md' : ''}
    ${severity ? severity.card : 'border-slate-200/80 bg-white'}`

  const content = (
    <>
      <span className={`flex items-center gap-1.5 text-xs font-medium ${severity ? severity.label : 'text-slate-500'}`}>
        {severity && <span className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${severity.dot}`} aria-hidden />}
        <span className="line-clamp-2">{formatLabel(kpi.label)}</span>
      </span>
      <span
        className={`text-2xl font-semibold tracking-tight tabular-nums sm:text-[1.65rem] ${severity ? severity.value : 'text-slate-900'}`}
      >
        {kpi.value === null ? <span className="text-slate-400">N/A</span> : formatKpiValue(kpi.value, kpi.format)}
      </span>
      {(kpi.detail || kpi.unavailable_reason) && (
        <span className="mt-auto text-xs text-slate-500">{kpi.detail ?? kpi.unavailable_reason}</span>
      )}
      {onClick && (
        <span className="text-xs font-medium text-slate-500 group-hover:text-slate-700" aria-hidden>
          Review →
        </span>
      )}
    </>
  )

  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={className}>
        {content}
      </button>
    )
  }
  return <div className={className}>{content}</div>
}
