export type WorkbookStatus = 'processing' | 'ready' | 'error'

export interface ColumnOut {
  name: string
  position: number
  inferred_type: string
  confidence: number
}

export interface WorksheetOut {
  name: string
  sheet_index: number
  row_count: number
  warning: string | null
  columns: ColumnOut[]
  sample_rows: Record<string, unknown>[]
}

export interface WorkbookOut {
  id: string
  original_filename: string
  display_title: string | null
  status: WorkbookStatus
  error_code: string | null
  error_message: string | null
  worksheets: WorksheetOut[]
}

export interface WorkbookSummary {
  id: string
  original_filename: string
  display_title: string | null
  status: WorkbookStatus
  created_at: string
}
