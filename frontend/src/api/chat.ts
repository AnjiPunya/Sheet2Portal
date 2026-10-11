import { apiFetch, throwApiError } from './client'
import type { PendingAction } from '../types/actions'
import type { ChatMessage, ChatResponse, ChatSuggestions } from '../types/chat'

/** `conversationId` enables business actions; `pendingAction` is the draft on screen (a "yes" confirms it). */
export interface ActionContext {
  conversationId: string
  pendingAction: PendingAction | null
}

export function actionBody(context?: ActionContext) {
  return context ? { conversation_id: context.conversationId, pending_action: context.pendingAction } : {}
}

export async function sendChatMessage(workbookId: string, messages: ChatMessage[], context?: ActionContext): Promise<ChatResponse> {
  const res = await apiFetch(`/api/workbooks/${workbookId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, ...actionBody(context) }),
  })
  if (!res.ok) return throwApiError(res)
  return res.json()
}

export async function fetchChatSuggestions(workbookId: string): Promise<ChatSuggestions> {
  const res = await apiFetch(`/api/workbooks/${workbookId}/chat/suggestions`)
  if (!res.ok) return throwApiError(res)
  return res.json()
}
