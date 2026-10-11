export type ChatRole = 'user' | 'assistant'

export interface ChatMessage {
  role: ChatRole
  content: string
}

export interface ChatReference {
  worksheet: string
  record_id: string
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
}

export interface ChatSuggestions {
  suggestions: string[]
}
