import type { ActionState } from './actions.ts'

export type ChatRole = 'user' | 'assistant'

export interface ChatMessage {
  role: ChatRole
  content: string
}

export interface ChatReferenceAction {
  kind: 'details' | 'related'
  /** "View details", "View Tasks" */
  label: string
  /** Sheet the action opens. */
  worksheet: string
  /** Number of related records (for "related"). */
  count?: number | null
}

export interface ChatReference {
  worksheet: string
  /** Real record id -- used for links, never shown. */
  record_id: string
  /** The record's name, e.g. "Green Meadows Apartments". */
  label?: string | null
  /** "Project", "Feed Log" */
  entity_label?: string | null
  actions?: ChatReferenceAction[]
}

export interface ChatToolCall {
  name: string
  arguments: Record<string, unknown>
}

export interface ChatResponse {
  message: string
  references: ChatReference[]
  tool_calls: ChatToolCall[]
  provider: string
  action?: ActionState | null
}

export interface ChatSuggestions {
  suggestions: string[]
}
