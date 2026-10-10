import { API_BASE_URL, throwApiError } from './client'
import type { PortalConfig, RecordDetail, RecordPage } from '../types/portal'

export async function fetchPortalConfig(workbookId: string): Promise<PortalConfig> {
  const res = await fetch(`${API_BASE_URL}/api/workbooks/${workbookId}/portal`)
  if (!res.ok) return throwApiError(res)
  return res.json()
}

export interface RecordQuery {
  search?: string
  status?: string
  page?: number
  pageSize?: number
}

export async function fetchRecords(
  workbookId: string,
  worksheet: string,
  query: RecordQuery = {},
): Promise<RecordPage> {
  const params = new URLSearchParams()
  if (query.search) params.set('search', query.search)
  if (query.status) params.set('status', query.status)
  params.set('page', String(query.page ?? 1))
  params.set('page_size', String(query.pageSize ?? 25))

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
