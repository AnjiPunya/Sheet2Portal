import { useRef, useState, type FocusEvent, type PointerEvent } from 'react'
import type { ChartSpec, GroupedBarChart, StatusBarsChart, StatusStackChart, TimeColumnsChart } from '../../types/portal'
import { formatCompact, formatFull, formatPercent, formatPeriod, INK, niceTicks, SERIES, STATUS } from '../../lib/chartFormat'
import { ChartCard, ChartTooltip, Legend, type TooltipState } from './ChartCard'
import { CategoryBars } from './CategoryBars'

/** Shared hover/focus tooltip positioning relative to the chart container. */
function useTooltip() {
  const ref = useRef<HTMLDivElement>(null)
  const [tip, setTip] = useState<TooltipState | null>(null)
  function show(e: PointerEvent<Element> | FocusEvent<Element>, content: Omit<TooltipState, 'x' | 'y'>) {
    const box = ref.current?.getBoundingClientRect()
    const mark = (e.currentTarget as Element).getBoundingClientRect()
    if (!box) return
    setTip({ ...content, x: mark.left + mark.width / 2 - box.left, y: mark.top - box.top })
  }
  return { ref, tip, show, hide: () => setTip(null) }
}

function GroupedBars({ chart }: { chart: GroupedBarChart }) {
  const { ref, tip, show, hide } = useTooltip()
  const max = Math.max(...chart.items.flatMap((i) => i.values), 1)
  return (
    <ChartCard
      title={chart.title}
      note={chart.note}
      legend={<Legend items={chart.series.map((label, i) => ({ label, color: SERIES[i] }))} />}
      table={{
        columns: ['', ...chart.series, 'Used'],
        rows: chart.items.map((i) => [i.label, formatFull(i.values[0]), formatFull(i.values[1]), formatPercent(i.values[1], i.values[0])]),
      }}
    >
      <div ref={ref} className="relative space-y-3.5">
        {chart.items.map((item) => (
          <div key={item.label} className="grid grid-cols-[minmax(0,9rem)_1fr] items-center gap-3 sm:grid-cols-[minmax(0,11rem)_1fr]">
            <div className="min-w-0">
              <p className="truncate text-sm text-slate-700" title={item.label}>
                {item.label}
              </p>
              {item.flag === 'over' && (
                <p className="flex items-center gap-1 text-[11px] font-medium text-red-700">
                  <span aria-hidden>▲</span> Over budget
                </p>
              )}
            </div>
            <div
              className="flex flex-col gap-0.5 rounded outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              tabIndex={0}
              onPointerEnter={(e) => show(e, { title: item.label, rows: chart.series.map((s, i) => ({ label: s, value: formatFull(item.values[i]), color: SERIES[i] })) })}
              onPointerLeave={hide}
              onFocus={(e) => show(e, { title: item.label, rows: chart.series.map((s, i) => ({ label: s, value: formatFull(item.values[i]), color: SERIES[i] })) })}
              onBlur={hide}
              aria-label={`${item.label}: ${chart.series.map((s, i) => `${s} ${formatFull(item.values[i])}`).join(', ')}`}
            >
              {item.values.map((value, i) => (
                <div key={i} className="flex items-center gap-2">
                  <div
                    className="h-2.5 rounded-r-[4px] transition-[width] duration-500"
                    style={{ width: `${Math.max((value / max) * 85, 0.5)}%`, backgroundColor: SERIES[i] }}
                  />
                  {i === 1 && <span className="text-[11px] text-slate-500 tabular-nums">{formatCompact(value)}</span>}
                </div>
              ))}
            </div>
          </div>
        ))}
        <ChartTooltip tip={tip} />
      </div>
    </ChartCard>
  )
}

function StatusStack({ chart }: { chart: StatusStackChart }) {
  const { ref, tip, show, hide } = useTooltip()
  const total = chart.segments.reduce((sum, s) => sum + s.value, 0)
  const visible = chart.segments.filter((s) => s.value > 0)
  return (
    <ChartCard
      title={chart.title}
      note={`${total} total`}
      // Status colors always ship with their label (warning is low-contrast on white).
      legend={
        <Legend
          items={chart.segments.map((s) => ({
            label: s.label,
            color: STATUS[s.status],
            detail: `${s.value} · ${formatPercent(s.value, total)}`,
          }))}
        />
      }
      table={{ columns: ['Status', 'Count', 'Share'], rows: chart.segments.map((s) => [s.label, s.value, formatPercent(s.value, total)]) }}
    >
      <div ref={ref} className="relative">
        <div className="flex h-6 w-full gap-[2px] overflow-hidden rounded-[4px]" role="img" aria-label={chart.segments.map((s) => `${s.label} ${s.value}`).join(', ')}>
          {visible.map((s) => (
            <div
              key={s.label}
              tabIndex={0}
              className="h-full outline-none transition-[flex-grow] duration-500 hover:brightness-110 focus-visible:brightness-110"
              style={{ flexGrow: s.value, flexBasis: 0, backgroundColor: STATUS[s.status] }}
              onPointerEnter={(e) => show(e, { title: s.label, rows: [{ label: 'Count', value: `${s.value} (${formatPercent(s.value, total)})` }] })}
              onPointerLeave={hide}
              onFocus={(e) => show(e, { title: s.label, rows: [{ label: 'Count', value: `${s.value} (${formatPercent(s.value, total)})` }] })}
              onBlur={hide}
            />
          ))}
        </div>
        <ChartTooltip tip={tip} />
      </div>
    </ChartCard>
  )
}

const PLOT_HEIGHT = 160

function TimeColumns({ chart }: { chart: TimeColumnsChart }) {
  const { ref, tip, show, hide } = useTooltip()
  const ticks = niceTicks(Math.max(...chart.points.map((p) => p.value), 1))
  const top = ticks[ticks.length - 1]
  const peak = chart.points.reduce((best, p) => (p.value > best.value ? p : best), chart.points[0])
  // Thin out x labels on dense axes.
  const every = Math.ceil(chart.points.length / 6)
  return (
    <ChartCard
      title={chart.title}
      note={`${formatFull(chart.total)} total · peak ${formatCompact(peak.value)} (${formatPeriod(peak.period, chart.unit)})`}
      table={{ columns: [chart.unit[0].toUpperCase() + chart.unit.slice(1), chart.series], rows: chart.points.map((p) => [formatPeriod(p.period, chart.unit), formatFull(p.value)]) }}
    >
      <div ref={ref} className="relative flex gap-2">
        <div className="relative w-10 shrink-0 text-right text-[10px] text-slate-400 tabular-nums" style={{ height: PLOT_HEIGHT }}>
          {ticks.map((t) => (
            <span key={t} className="absolute right-0" style={{ bottom: `${(t / top) * 100}%`, transform: 'translateY(50%)' }}>
              {formatCompact(t)}
            </span>
          ))}
        </div>
        <div className="min-w-0 flex-1">
          <div className="relative" style={{ height: PLOT_HEIGHT }}>
            {ticks.map((t) => (
              <div key={t} className="absolute inset-x-0 border-t" style={{ bottom: `${(t / top) * 100}%`, borderColor: t === 0 ? INK.axis : INK.grid }} />
            ))}
            <div className="absolute inset-0 flex items-end gap-[2px] px-0.5">
              {chart.points.map((p) => (
                <div
                  key={p.period}
                  tabIndex={0}
                  className="group flex h-full flex-1 items-end justify-center outline-none"
                  onPointerEnter={(e) => show(e, { title: formatPeriod(p.period, chart.unit), rows: [{ label: chart.series, value: formatFull(p.value), color: SERIES[0] }] })}
                  onPointerLeave={hide}
                  onFocus={(e) => show(e, { title: formatPeriod(p.period, chart.unit), rows: [{ label: chart.series, value: formatFull(p.value), color: SERIES[0] }] })}
                  onBlur={hide}
                  aria-label={`${formatPeriod(p.period, chart.unit)}: ${formatFull(p.value)}`}
                >
                  <div
                    className="w-full max-w-6 rounded-t-[4px] transition-[height] duration-500 group-hover:brightness-110 group-focus-visible:ring-2 group-focus-visible:ring-indigo-400"
                    style={{ height: `${(p.value / top) * 100}%`, minHeight: p.value > 0 ? 2 : 0, backgroundColor: SERIES[0] }}
                  />
                </div>
              ))}
            </div>
          </div>
          <div className="mt-1.5 flex gap-[2px] px-0.5 text-[10px] text-slate-400">
            {chart.points.map((p, i) => (
              <span key={p.period} className="flex-1 truncate text-center">
                {i % every === 0 ? formatPeriod(p.period, chart.unit).replace('Wk of ', '') : ''}
              </span>
            ))}
          </div>
        </div>
        <ChartTooltip tip={tip} />
      </div>
    </ChartCard>
  )
}

function StatusBars({ chart }: { chart: StatusBarsChart }) {
  const total = chart.items.reduce((s, i) => s + i.value, 0)
  return (
    <ChartCard
      title={chart.title}
      note={`${total} total`}
      table={{ columns: ['Status', 'Count', 'Share'], rows: chart.items.map((i) => [i.label, i.value, formatPercent(i.value, total)]) }}
    >
      <CategoryBars items={chart.items} />
    </ChartCard>
  )
}

export function DashboardCharts({ charts }: { charts: ChartSpec[] }) {
  if (charts.length === 0) return null
  return (
    <section className="space-y-3">
      <h2 className="section-label">Insights</h2>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {charts.map((chart) => {
          switch (chart.kind) {
            case 'grouped_bar':
              return <GroupedBars key={chart.id} chart={chart} />
            case 'status_stack':
              return <StatusStack key={chart.id} chart={chart} />
            case 'time_columns':
              return <TimeColumns key={chart.id} chart={chart} />
            case 'status_bars':
              return <StatusBars key={chart.id} chart={chart} />
            default:
              return null
          }
        })}
      </div>
    </section>
  )
}
