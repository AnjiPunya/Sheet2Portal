import { API_BASE_URL, throwApiError } from './client'
import type { PortalConfig, RecordDetail, RecordPage } from '../types/portal'
import { buildRecordParams, type RecordQuery } from '../lib/recordQuery'

export async function fetchPortalConfig(workbookId: string): Promise<PortalConfig> {
  const res = await fetch(`${API_BASE_URL}/api/workbooks/${workbookId}/portal`)
  if (!res.ok) return throwApiError(res)
  return res.json()
}

export async function fetchRecords(
  workbookId: string,
  worksheet: string,
  query: RecordQuery = {},
): Promise<RecordPage> {
  const params = buildRecordParams(query)
  const res = await fetch(
    `${API_BASE_URL}/api/workbooks/${workbookId}/worksheets/${encodeURIComponent(worksheet)}/records?${params}`,
  )
  if (!res.ok) return throwApiError(res)
  return res.json()
}

export async function fetchRecordDetail(
  workbookId: string,
  worksheet: string,
  recordId: string,
): Promise<RecordDetail> {
  const res = await fetch(
    `${API_BASE_URL}/api/workbooks/${workbookId}/worksheets/${encodeURIComponent(worksheet)}/records/${recordId}`,
  )
  if (!res.ok) return throwApiError(res)
  return res.json()
}
