export type FieldType = 'string' | 'int' | 'float' | 'date' | 'bool'

export interface FieldSpec {
  name: string
  label: string
  type: FieldType
  input: 'text' | 'number' | 'date' | 'checkbox' | 'select' | 'tel' | 'email' | 'time'
  role: string
  required: boolean
  readonly: boolean
  /** Human description of the calculation, e.g. "Amount = Quantity × Unit Cost (from Materials)". */
  computed: string | null
  options: string[] | null
  suggestions: string[] | null
  min: number | null
  auto: 'next_id' | null
  placeholder?: string | null
  default?: string | number | null
  workflow?: boolean
  link?: { entity: string; column: string }
  /** A value looked up from the record selected in another field (e.g. a material's unit cost). */
  lookup?: { from: string; entity: string; defaults: Record<string, string | number | null> }
  /** Display labels for select options, e.g. "POND-001" -> "POND-001 · North Pond". */
  option_labels?: Record<string, string> | null
  max?: number | null
  /** Text formats checked on both sides. */
  format?: 'tel' | 'email' | 'time' | null
  /** One-line explanation of the field's rule (auto-filled, limits...). */
  hint?: string | null
  /** IDs generated with a prefix chosen by another field (Party Type -> SUP-/BUY-). */
  auto_by?: { column: string; next: Record<string, string | null> }
  /** This date can't be before the named date field. */
  after?: string
  /** This number can't exceed the sum of these fields (Used <= Opening + Received). */
  max_sum?: string[]
  /** This number can't exceed the stock available in the record picked in `from`. */
  max_from?: { from: string; entity: string; available: Record<string, number | null> }
}

export interface FormulaSpec {
  target: string
  factors: { column: string; lookup_from: string | null }[]
  description: string
}

export interface WorkflowSpec {
  status_column: string
  pending: string
  approved: string
  rejected: string
}

export interface EntitySchema {
  worksheet: string
  label: string
  singular_label: string
  identifier_column: string | null
  title_column: string | null
  fields: FieldSpec[]
  formulas: FormulaSpec[]
  workflow: WorkflowSpec | null
  done_statuses: string[]
  can_create: boolean
}

export interface RecordActions {
  edit: boolean
  delete: boolean
  approve: boolean
  reject: boolean
  resubmit: boolean
}

export interface RecordWriteResult {
  id: string
  data: Record<string, unknown>
  actions: RecordActions
}

export interface RecordEvent {
  id: string
  action: 'created' | 'updated' | 'deleted' | 'approved' | 'rejected' | 'resubmitted'
  user_name: string
  from_status: string | null
  to_status: string | null
  comment: string | null
  changes: Record<string, [unknown, unknown]>
  created_at: string
}

export interface RecordActivity {
  actions: RecordActions
  history: RecordEvent[]
}

export type DecisionAction = 'approve' | 'reject' | 'resubmit'
