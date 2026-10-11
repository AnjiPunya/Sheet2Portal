import { API_BASE_URL, throwApiError } from './client'
import type { WorkbookOut } from '../types/workbook'

export async function uploadWorkbook(file: File): Promise<WorkbookOut> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${API_BASE_URL}/api/workbooks`, { method: 'POST', body: formData })
  if (!res.ok) return throwApiError(res)
  return res.json()
}

export async function fetchWorkbook(id: string): Promise<WorkbookOut> {
  const res = await fetch(`${API_BASE_URL}/api/workbooks/${id}`)
  if (!res.ok) return throwApiError(res)
  return res.json()
}

export async function updateWorkbookTitle(id: string, title: string): Promise<WorkbookOut> {
  const res = await fetch(`${API_BASE_URL}/api/workbooks/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  if (!res.ok) return throwApiError(res)
  return res.json()
}
