export interface ColumnProfile {
  name: string
  position: number
  inferred_type: string
  type_confidence: number
  role: string
  role_confidence: number
}

export interface StatusBreakdownItem {
  value: string
  count: number
  is_risk: boolean
}

export type KPIFormat = 'number' | 'percent' | 'currency'
export type Severity = 'critical' | 'warning' | null

export interface KPIDefinition {
  key: string
  label: string
  entity: string | null
  value: number | null
  format: KPIFormat
  severity: Severity
  detail: string | null
  unavailable_reason: string | null
}

export type EntityLayout = 'cards' | 'table'

export interface LowStockStrategy {
  type: 'direct' | 'flow'
  quantity_column: string | null
  threshold_column: string | null
  opening_column: string | null
  inbound_column: string | null
  outbound_column: string | null
}

export interface EntityConfig {
  worksheet: string
  label: string
  singular_label: string
  icon: string
  identifier_column: string | null
  title_column: string | null
  status_column: string | null
  columns: ColumnProfile[]
  layout: EntityLayout
  row_count: number
  status_breakdown: StatusBreakdownItem[]
  kpis: KPIDefinition[]
  low_stock_strategy: LowStockStrategy | null
  /** Documentation sheet (README, Data Dictionary...): read-only, no KPIs. */
  reference?: boolean
}

export interface RelationshipCandidate {
  from_entity: string
  from_column: string
  to_entity: string
  to_column: string
  match_rate: number
  confidence: 'high' | 'medium' | 'low'
}

export interface PortalConfig {
  title: string
  entities: EntityConfig[]
  kpis: KPIDefinition[]
  alerts: KPIDefinition[]
  relationships: RelationshipCandidate[]
  primary_entity: string | null
  /** Detected business domain (e.g. "construction", "retail", "generic"); theming only. */
  domain?: string
  /** Charts chosen by the backend from the workbook's data. */
  charts?: ChartSpec[]
}

export interface RecordItem {
  id: string
  data: Record<string, unknown>
  /** Readable labels for reference columns, e.g. Project_ID -> "Green Meadows Apartments · Kompally". */
  display?: Record<string, string>
}

export interface RecordPage {
  records: RecordItem[]
  total: number
  page: number
  page_size: number
}

export interface RelatedGroup {
  entity: string
  relationship: string
  records: RecordItem[]
}

export interface RecordDetail {
  id: string
  data: Record<string, unknown>
  display?: Record<string, string>
  related: RelatedGroup[]
}

export interface GroupedBarChart {
  id: string
  kind: 'grouped_bar'
  title: string
  entity: string
  series: [string, string]
  items: { label: string; values: [number, number]; flag: 'over' | null }[]
  note: string | null
}

export interface StatusStackChart {
  id: string
  kind: 'status_stack'
  title: string
  entity: string
  segments: { label: string; value: number; status: 'good' | 'warning' | 'critical' | 'neutral' }[]
}

export interface TimeColumnsChart {
  id: string
  kind: 'time_columns'
  title: string
  entity: string
  unit: 'day' | 'week' | 'month' | 'quarter'
  series: string
  points: { period: string; value: number }[]
  total: number
}

export interface StatusBarsChart {
  id: string
  kind: 'status_bars'
  title: string
  entity: string
  items: { label: string; value: number; risk: boolean }[]
}

export type ChartSpec = GroupedBarChart | StatusStackChart | TimeColumnsChart | StatusBarsChart
