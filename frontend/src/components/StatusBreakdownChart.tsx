import type { StatusBreakdownItem } from '../types/portal'
import { CategoryBars } from './charts/CategoryBars'

/** Status breakdown on an entity page -- same colours, icons and labels as
 * the dashboard charts (see lib/chartFormat.ts). */
export function StatusBreakdownChart({ items, max = 6 }: { items: StatusBreakdownItem[]; max?: number }) {
  if (items.length < 2) return null
  return <CategoryBars items={items.map((i) => ({ label: i.value, value: i.count }))} max={max} />
}
