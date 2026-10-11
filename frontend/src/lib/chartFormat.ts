// Chart tokens and number/date formatting (pure, unit-testable).
// Colors: the dataviz reference palette's light values, validated against
// the white chart surface (scripts/validate_palette.js: all checks pass).

export const SERIES = ['#2a78d6', '#eb6834'] as const // categorical slots 1-2, fixed order
export const STATUS = { good: '#0ca30c', warning: '#fab219', critical: '#d03b3b', neutral: '#c3c2b7' } as const
export const INK = { primary: '#0b0b0b', secondary: '#52514e', muted: '#898781', grid: '#e1e0d9', axis: '#c3c2b7' } as const

const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 })
const full = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })

export const formatCompact = (n: number) => (Math.abs(n) >= 1000 ? compact.format(n) : full.format(n))
export const formatFull = (n: number) => full.format(n)

export function formatPercent(part: number, whole: number): string {
  if (whole <= 0) return '0%'
  return `${Math.round((part / whole) * 100)}%`
}

/** Clean axis ticks: 0 .. a round maximum >= `max`, in `count` steps. */
export function niceTicks(max: number, count = 4): number[] {
  if (max <= 0) return [0]
  const rough = max / count
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? 10 * magnitude
  const ticks: number[] = []
  for (let v = 0; v <= max + step * 0.0001; v += step) ticks.push(Math.round(v * 1e6) / 1e6)
  if (ticks[ticks.length - 1] < max) ticks.push(ticks[ticks.length - 1] + step)
  return ticks
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Axis/tooltip label for a period start date (ISO yyyy-mm-dd). */
export function formatPeriod(iso: string, unit: 'day' | 'week' | 'month' | 'quarter'): string {
  const [y, m, d] = iso.split('-').map(Number)
  if (unit === 'quarter') return `Q${Math.floor((m - 1) / 3) + 1} ${y}`
  if (unit === 'month') return `${MONTHS[m - 1]} ${y}`
  const label = `${d} ${MONTHS[m - 1]}`
  return unit === 'week' ? `Wk of ${label}` : label
}

// --- status colours -----------------------------------------------------------
// Statuses are coloured by what they mean (consistent across every chart),
// and always shown with an icon + text label so colour is never the only
// cue (red/green and amber don't separate for colour-blind readers).
// Non-status categories use the categorical palette in fixed order.

export type StatusTone = 'done' | 'progress' | 'waiting' | 'attention' | 'risk' | 'neutral'

export const TONES: Record<StatusTone, { color: string; icon: string; meaning: string }> = {
  done: { color: '#0ca30c', icon: '✓', meaning: 'done' },
  progress: { color: '#2a78d6', icon: '◐', meaning: 'in progress' },
  waiting: { color: '#fab219', icon: '○', meaning: 'waiting' },
  attention: { color: '#ec835a', icon: '!', meaning: 'needs attention' },
  risk: { color: '#d03b3b', icon: '▲', meaning: 'at risk' },
  neutral: { color: '#898781', icon: '–', meaning: 'inactive' },
}

// Categorical slots (validated reference palette, fixed order).
export const CATEGORICAL = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'] as const

const TONE_RULES: [StatusTone, RegExp][] = [
  ['risk', /\b(at risk|blocked|overdue|rejected|delayed|critical|failed|escalated)\b/i],
  ['neutral', /\b(cancel+ed|inactive|on hold|paused|suspended|returned|archived|refunded)\b/i],
  ['done', /\b(done|complete|completed|closed|resolved|paid|delivered|approved|harvested|received|fulfilled|finished|settled)\b/i],
  ['attention', /\b(follow-?up|due|attention|escalate)\b/i],
  ['progress', /\b(in progress|ongoing|investigating|monitoring|processing|shipped|ordered|in transit|active|(?<!not )started|working|review)\b/i],
  ['waiting', /\b(open|pending|not started|to do|new|requested|awaiting|planned|draft|submitted)\b/i],
]

/** The tone a status label conveys, or null for a plain category. */
export function statusTone(label: string): StatusTone | null {
  for (const [tone, pattern] of TONE_RULES) if (pattern.test(label)) return tone
  return null
}

/** Colours for a set of chart categories: status meaning where recognisable,
 * otherwise categorical slots in order (stable per position in the list). */
export function categoryColors(labels: string[]): { color: string; tone: StatusTone | null }[] {
  const tones = labels.map(statusTone)
  const isStatusChart = tones.filter(Boolean).length >= Math.ceil(labels.length / 2)
  let slot = 0
  return labels.map((_, i) => {
    const tone = isStatusChart ? tones[i] : null
    if (tone) return { color: TONES[tone].color, tone }
    return { color: CATEGORICAL[slot++ % CATEGORICAL.length], tone: null }
  })
}
