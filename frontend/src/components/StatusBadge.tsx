import { statusTone, TONES, type StatusTone } from '../lib/chartFormat'

// Same meanings as the charts (lib/chartFormat.ts), as light badges with the
// tone's icon, so a status looks the same everywhere in the portal.
const TONE_BADGE: Record<StatusTone, string> = {
  done: 'bg-green-50 text-green-800 ring-green-200',
  progress: 'bg-blue-50 text-blue-800 ring-blue-200',
  waiting: 'bg-amber-50 text-amber-800 ring-amber-200',
  attention: 'bg-orange-50 text-orange-800 ring-orange-200',
  risk: 'bg-red-50 text-red-700 ring-red-200',
  neutral: 'bg-slate-100 text-slate-600 ring-slate-200',
}

// Plain categories (not statuses) keep a stable colour per value.
const PALETTE = [
  'bg-blue-50 text-blue-800 ring-blue-200',
  'bg-emerald-50 text-emerald-800 ring-emerald-200',
  'bg-purple-50 text-purple-800 ring-purple-200',
  'bg-slate-100 text-slate-700 ring-slate-200',
  'bg-cyan-50 text-cyan-800 ring-cyan-200',
  'bg-teal-50 text-teal-800 ring-teal-200',
]

function hashString(value: string): number {
  let hash = 0
  for (let i = 0; i < value.length; i++) hash = (hash * 31 + value.charCodeAt(i)) >>> 0
  return hash
}

export function StatusBadge({ value, isRisk }: { value: string; isRisk?: boolean }) {
  const tone = statusTone(value) ?? (isRisk ? 'risk' : null)
  const className = tone ? TONE_BADGE[tone] : PALETTE[hashString(value) % PALETTE.length]
  return (
    <span className={`inline-flex w-fit items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${className}`}>
      {tone && (
        <span aria-hidden className="text-[10px] leading-none">
          {TONES[tone].icon}
        </span>
      )}
      {value}
    </span>
  )
}
