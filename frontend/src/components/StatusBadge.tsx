const PALETTE = [
  'bg-blue-100 text-blue-700',
  'bg-emerald-100 text-emerald-700',
  'bg-purple-100 text-purple-700',
  'bg-slate-200 text-slate-700',
  'bg-cyan-100 text-cyan-700',
  'bg-teal-100 text-teal-700',
]

function hashString(value: string): number {
  let hash = 0
  for (let i = 0; i < value.length; i++) hash = (hash * 31 + value.charCodeAt(i)) >>> 0
  return hash
}

export function StatusBadge({ value, isRisk }: { value: string; isRisk?: boolean }) {
  const className = isRisk ? 'bg-red-100 text-red-700' : PALETTE[hashString(value) % PALETTE.length]
  return (
    <span className={`inline-flex w-fit items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}>
      {value}
    </span>
  )
}
