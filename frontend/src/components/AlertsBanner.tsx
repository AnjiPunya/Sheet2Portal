import type { KPIDefinition } from '../types/portal'
import { alertText } from '../lib/alerts'
import { usePortalNav } from './portalContext'

export function AlertsBanner({
  alerts,
  onSelectEntity,
}: {
  alerts: KPIDefinition[]
  onSelectEntity: (worksheet: string) => void
}) {
  const nav = usePortalNav()
  if (alerts.length === 0) return null

  const hasCritical = alerts.some((a) => a.severity === 'critical')
  const items = alerts.map((alert) => ({ alert, text: alertText(alert, alert.entity ? nav.labelFor(alert.entity) : null) }))

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-amber-200 bg-gradient-to-r from-amber-50 to-orange-50/60 p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <svg
          className={`mt-0.5 h-5 w-5 flex-shrink-0 ${hasCritical ? 'text-red-500' : 'text-amber-500'}`}
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden
        >
          <path
            fillRule="evenodd"
            d="M8.257 3.099c.765-1.36 2.72-1.36 3.486 0l6.517 11.59c.75 1.334-.213 2.98-1.742 2.98H3.483c-1.53 0-2.493-1.646-1.743-2.98l6.517-11.59zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 8a1 1 0 100-2 1 1 0 000 2z"
            clipRule="evenodd"
          />
        </svg>
        <div>
          <p className="font-semibold text-slate-800">Action required</p>
          <p className="text-sm text-slate-600">
            {alerts.length} {alerts.length === 1 ? 'item needs' : 'items need'} attention. Each opens the records behind it.
          </p>
        </div>
      </div>
      {/* One button per alert, each naming its sheet -- no duplicates elsewhere on the dashboard. */}
      <div className="flex flex-wrap gap-2">
        {items.map(({ alert, text }) => (
          <button
            key={alert.key}
            onClick={() => alert.entity && onSelectEntity(alert.entity)}
            className={`inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium text-white shadow-sm transition-colors
              ${alert.severity === 'critical' ? 'bg-red-600 hover:bg-red-700' : 'bg-amber-600 hover:bg-amber-700'}`}
          >
            <span>{text}</span>
            <span className="rounded-full bg-white/25 px-1.5 text-xs font-semibold tabular-nums">{alert.value}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
