import { jsonRequest } from './client'
import type { ActionResult } from '../types/actions'

export function confirmAction(workbookId: string, draftId: string, token: string, conversationId: string): Promise<ActionResult> {
  return jsonRequest(`/api/workbooks/${workbookId}/actions/${draftId}/confirm`, 'POST', { token, conversation_id: conversationId })
}

export function cancelAction(workbookId: string, draftId: string, conversationId: string): Promise<ActionResult> {
  return jsonRequest(`/api/workbooks/${workbookId}/actions/${draftId}/cancel`, 'POST', { conversation_id: conversationId })
}
