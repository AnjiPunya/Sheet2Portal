import { jsonRequest } from './client'
import type { DecisionAction, EntitySchema, RecordActivity, RecordWriteResult } from '../types/records'

const base = (workbookId: string, worksheet: string) =>
  `/api/workbooks/${workbookId}/worksheets/${encodeURIComponent(worksheet)}`

export function fetchEntitySchema(workbookId: string, worksheet: string): Promise<EntitySchema> {
  return jsonRequest(`${base(workbookId, worksheet)}/schema`, 'GET')
}

export function createRecord(workbookId: string, worksheet: string, data: Record<string, unknown>): Promise<RecordWriteResult> {
  return jsonRequest(`${base(workbookId, worksheet)}/records`, 'POST', { data })
}

export function updateRecord(
  workbookId: string,
  worksheet: string,
  recordId: string,
  data: Record<string, unknown>,
): Promise<RecordWriteResult> {
  return jsonRequest(`${base(workbookId, worksheet)}/records/${recordId}`, 'PATCH', { data })
}

export function deleteRecord(workbookId: string, worksheet: string, recordId: string): Promise<void> {
  return jsonRequest(`${base(workbookId, worksheet)}/records/${recordId}`, 'DELETE')
}

export function decideRecord(
  workbookId: string,
  worksheet: string,
  recordId: string,
  action: DecisionAction,
  comment?: string,
): Promise<RecordWriteResult> {
  return jsonRequest(`${base(workbookId, worksheet)}/records/${recordId}/decision`, 'POST', { action, comment: comment || null })
}

export function fetchRecordActivity(workbookId: string, worksheet: string, recordId: string): Promise<RecordActivity> {
  return jsonRequest(`${base(workbookId, worksheet)}/records/${recordId}/activity`, 'GET')
}
