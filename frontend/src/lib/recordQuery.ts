import type { RelatedFilter } from './portalView.ts'

export interface RecordQuery {
  search?: string
  status?: string
  related?: RelatedFilter
  page?: number
  pageSize?: number
}

/** Query-string for the records endpoint. The related filter sends only the
 * parent's worksheet + id; the backend resolves the link through the
 * workbook's detected relationships. */
export function buildRecordParams(query: RecordQuery = {}): URLSearchParams {
  const params = new URLSearchParams()
  if (query.search) params.set('search', query.search)
  if (query.status) params.set('status', query.status)
  if (query.related) {
    params.set('related_worksheet', query.related.worksheet)
    params.set('related_record_id', query.related.recordId)
  }
  params.set('page', String(query.page ?? 1))
  params.set('page_size', String(query.pageSize ?? 25))
  return params
}
