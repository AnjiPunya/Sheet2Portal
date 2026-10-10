import type { LowStockStrategy } from '../types/portal'

function numeric(value: unknown): number | null {
  return typeof value === 'number' ? value : null
}

/** Mirrors backend `current_quantity()` in app/services/analysis/kpis.py. */
export function currentQuantity(row: Record<string, unknown>, strategy: LowStockStrategy): number | null {
  if (strategy.type === 'direct') {
    return strategy.quantity_column ? numeric(row[strategy.quantity_column]) : null
  }
  const opening = strategy.opening_column ? numeric(row[strategy.opening_column]) : null
  if (opening === null) return null
  const inbound = (strategy.inbound_column ? numeric(row[strategy.inbound_column]) : null) ?? 0
  const outbound = (strategy.outbound_column ? numeric(row[strategy.outbound_column]) : null) ?? 0
  return opening + inbound - outbound
}

export function isLowStock(row: Record<string, unknown>, strategy: LowStockStrategy | null): boolean {
  if (!strategy || !strategy.threshold_column) return false
  const quantity = currentQuantity(row, strategy)
  const threshold = numeric(row[strategy.threshold_column])
  if (quantity === null || threshold === null) return false
  return quantity <= threshold
}
