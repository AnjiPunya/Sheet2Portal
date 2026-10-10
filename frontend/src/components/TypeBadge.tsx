const COLORS: Record<string, string> = {
  int: 'bg-blue-100 text-blue-700',
  float: 'bg-blue-100 text-blue-700',
  date: 'bg-purple-100 text-purple-700',
  bool: 'bg-emerald-100 text-emerald-700',
  string: 'bg-slate-100 text-slate-700',
  unknown: 'bg-amber-100 text-amber-700',
}

export function TypeBadge({ type, confidence }: { type: string; confidence: number }) {
  const className = COLORS[type] ?? COLORS.unknown
  return (
    <span
      className={`inline-flex w-fit items-center rounded-full px-2 py-0.5 text-xs font-medium ${className}`}
      title={`Confidence: ${Math.round(confidence * 100)}%`}
    >
      {type}
    </span>
  )
}
