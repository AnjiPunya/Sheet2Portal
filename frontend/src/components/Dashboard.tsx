import type { PortalConfig } from '../types/portal'
import { KPICard } from './KPICard'
import { AlertsBanner } from './AlertsBanner'
import { EntityView } from './EntityView'

export function Dashboard({
  workbookId,
  config,
  titleColumnByWorksheet,
  onNavigateEntity,
}: {
  workbookId: string
  config: PortalConfig
  titleColumnByWorksheet: Record<string, string | null>
  onNavigateEntity: (worksheet: string) => void
}) {
  const primaryEntity = config.entities.find((e) => e.worksheet === config.primary_entity) ?? null
  const alertKeys = new Set(config.alerts.map((a) => a.key))

  const summaryKpis = primaryEntity
    ? primaryEntity.kpis.filter((k) => !alertKeys.has(k.key))
    : config.kpis.filter((k) => k.key.endsWith(':count') && !alertKeys.has(k.key)).slice(0, 4)

  // The banner below already lists every alert (text summary + a button
  // each), so the card grid only needs to headline the most pressing ones --
  // otherwise a workbook with many entities turns the top of the dashboard
  // into a wall of identical-looking cards.
  const severityWeight = (severity: string | null) => (severity === 'critical' ? 0 : 1)
  const headlineAlerts = [...config.alerts]
    .sort((a, b) => severityWeight(a.severity) - severityWeight(b.severity) || (b.value ?? 0) - (a.value ?? 0))
    .slice(0, 4)

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {summaryKpis.map((kpi) => (
          <KPICard key={kpi.key} kpi={kpi} />
        ))}
        {headlineAlerts.map((alert) => (
          <KPICard key={alert.key} kpi={alert} onClick={() => alert.entity && onNavigateEntity(alert.entity)} />
        ))}
      </div>

      <AlertsBanner alerts={config.alerts} onSelectEntity={onNavigateEntity} />

      {primaryEntity ? (
        <div>
          <div className="mb-3">
            <h2 className="text-lg font-semibold text-slate-800">{primaryEntity.label} Portfolio</h2>
            <p className="text-sm text-slate-400">Live data from the uploaded workbook</p>
          </div>
          <EntityView
            key={primaryEntity.worksheet}
            workbookId={workbookId}
            entity={primaryEntity}
            titleColumnByWorksheet={titleColumnByWorksheet}
            onNavigateEntity={onNavigateEntity}
            embedded
          />
        </div>
      ) : (
        config.entities.length === 0 && (
          <p className="text-sm text-slate-400">No usable worksheets were found in this workbook.</p>
        )
      )}
    </div>
  )
}
