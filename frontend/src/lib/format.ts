import type { KPIFormat } from '../types/portal'

export function formatKpiValue(value: number, format: KPIFormat): string {
  if (format === 'percent') return `${value}%`
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value)
}

export function formatCellValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}
