import type { PortalConfig } from '../types/portal'
import { usePortalNav } from './portalContext'
import { KPICard } from './KPICard'
import { AlertsBanner } from './AlertsBanner'
import { EntityView } from './EntityView'
import { DashboardHero } from './DashboardHero'
import { DashboardCharts } from './charts/DashboardCharts'

export function Dashboard({ workbookId, config }: { workbookId: string; config: PortalConfig }) {
  const nav = usePortalNav()
  const primaryEntity = config.entities.find((e) => e.worksheet === config.primary_entity) ?? null
  const alertKeys = new Set(config.alerts.map((a) => a.key))

  const summaryKpis = primaryEntity
    ? primaryEntity.kpis.filter((k) => !alertKeys.has(k.key))
    : config.kpis.filter((k) => k.key.endsWith(':count') && !alertKeys.has(k.key)).slice(0, 4)

  return (
    <div className="space-y-8">
      <DashboardHero config={config} />

      <section className="space-y-3">
        <h2 className="section-label">Overview</h2>
        <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 lg:grid-cols-4">
          {summaryKpis.map((kpi) => (
            <KPICard key={kpi.key} kpi={kpi} />
          ))}
        </div>
      </section>

      <AlertsBanner alerts={config.alerts} onSelectEntity={nav.openEntity} />

      <DashboardCharts charts={config.charts ?? []} />

      {primaryEntity ? (
        <section className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-slate-900">
                {nav.labelFor(primaryEntity.worksheet)} Portfolio
              </h2>
              <p className="mt-0.5 text-sm text-slate-500">Live data from the uploaded workbook</p>
            </div>
            <button
              onClick={() => nav.openEntity(primaryEntity.worksheet)}
              className="text-sm font-medium text-indigo-600 hover:text-indigo-700"
            >
              Open {nav.labelFor(primaryEntity.worksheet)} →
            </button>
          </div>
          <EntityView key={primaryEntity.worksheet} workbookId={workbookId} entity={primaryEntity} embedded />
        </section>
      ) : (
        config.entities.length === 0 && (
          <p className="text-sm text-slate-500">No usable worksheets were found in this workbook.</p>
        )
      )}
    </div>
  )
}
