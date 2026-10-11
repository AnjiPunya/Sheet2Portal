import type { KPIFormat } from '../types/portal.ts'

export function formatKpiValue(value: number, format: KPIFormat): string {
  if (format === 'percent') return `${value}%`
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value)
}

export function formatCellValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

// Roles whose numbers are amounts or counts: shown with thousands separators.
// Everything else (IDs, phone numbers, years, pH...) is shown as entered.
const GROUPED_ROLES = new Set(['amount', 'budget_amount', 'actual_amount', 'quantity', 'threshold'])

/** A cell value formatted for display, using its column's role when known. */
export function formatFieldValue(value: unknown, role?: string | null): string {
  if (typeof value === 'number' && role && GROUPED_ROLES.has(role)) {
    return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value)
  }
  return formatCellValue(value)
}
