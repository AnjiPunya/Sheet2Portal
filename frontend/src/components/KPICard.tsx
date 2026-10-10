import type { KPIDefinition } from '../types/portal'
import { formatKpiValue } from '../lib/format'

const SEVERITY_STYLES: Record<string, string> = {
  critical: 'border-red-200 bg-red-50',
  warning: 'border-amber-200 bg-amber-50',
}
const SEVERITY_VALUE_TEXT: Record<string, string> = {
  critical: 'text-red-700',
  warning: 'text-amber-700',
}
const SEVERITY_LABEL_TEXT: Record<string, string> = {
  critical: 'text-red-600',
  warning: 'text-amber-600',
}

export function KPICard({ kpi, onClick }: { kpi: KPIDefinition; onClick?: () => void }) {
  const severity = kpi.severity
  const className = `flex flex-col gap-1 rounded-xl border p-4 text-left shadow-sm transition-shadow w-full
    ${onClick ? 'cursor-pointer hover:shadow-md' : ''}
    ${severity ? SEVERITY_STYLES[severity] : 'border-slate-200 bg-white'}`

  const content = (
    <>
      <span
        className={`text-xs font-medium uppercase tracking-wide ${severity ? SEVERITY_LABEL_TEXT[severity] : 'text-slate-500'}`}
      >
        {kpi.label}
      </span>
      <span className={`text-2xl font-semibold ${severity ? SEVERITY_VALUE_TEXT[severity] : 'text-slate-900'}`}>
        {kpi.value === null ? 'N/A' : formatKpiValue(kpi.value, kpi.format)}
      </span>
      {(kpi.detail || kpi.unavailable_reason) && (
        <span className="text-xs text-slate-400">{kpi.detail ?? kpi.unavailable_reason}</span>
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
