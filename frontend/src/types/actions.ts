export type ActionStateName = 'clarification_required' | 'awaiting_confirmation' | 'completed' | 'cancelled' | 'failed'

export interface ActionField {
  name: string
  label: string
  value: unknown
  previous?: unknown
  computed: boolean
}

export interface ActionPreview {
  action: 'create' | 'update' | 'delete' | 'approve' | 'reject' | 'resubmit'
  worksheet: string
  entity_label: string
  record_id: string | null
  record_label: string
  fields: ActionField[]
  status_change: { from: string; to: string } | null
  consequences: string[]
  comment: string | null
}

export interface ActionCandidate {
  record_id: string
  label: string
  status: string | null
}

/** A business-action draft or outcome, as returned by /chat, /voice/respond and /actions/*. */
export interface ActionState {
  state: ActionStateName
  draft_id: string | null
  token: string | null
  expires_at: string | null
  preview: ActionPreview | null
  missing: { name: string; label: string; message: string }[]
  errors: Record<string, string>
  candidates: ActionCandidate[]
  code: string | null
  message: string | null
  record_id?: string | null
}

/** The draft the client is showing; sent with the next message so a plain "yes" confirms exactly it. */
export interface PendingAction {
  draft_id: string
  token: string
}

export interface ActionResult {
  message: string
  action: ActionState
}
