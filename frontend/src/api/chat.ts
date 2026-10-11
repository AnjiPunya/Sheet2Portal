import { API_BASE_URL, throwApiError } from './client'
import type { ChatMessage, ChatResponse, ChatSuggestions } from '../types/chat'

export async function sendChatMessage(workbookId: string, messages: ChatMessage[]): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE_URL}/api/workbooks/${workbookId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
  })
  if (!res.ok) return throwApiError(res)
  return res.json()
}

export async function fetchChatSuggestions(workbookId: string): Promise<ChatSuggestions> {
  const res = await fetch(`${API_BASE_URL}/api/workbooks/${workbookId}/chat/suggestions`)
  if (!res.ok) return throwApiError(res)
  return res.json()
}
