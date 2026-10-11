import type { KPIDefinition } from '../types/portal.ts'

/** "Pending" alone is ambiguous when two sheets have pending records, so a
 * status alert names its sheet: "Pending · Expenses Payments". Alerts whose
 * label already says what they are (Low-Stock Alerts, Overdue Tasks) stay as
 * is. Labels aren't re-formatted: they're either already readable (from the
 * backend) or the workbook's own status wording ("Follow-up due"). */
export function alertText(alert: Pick<KPIDefinition, 'key' | 'label'>, entityLabel: string | null): string {
  const isStatusAlert = alert.key.includes(':status:')
  return isStatusAlert && entityLabel ? `${alert.label} · ${entityLabel}` : alert.label
}
