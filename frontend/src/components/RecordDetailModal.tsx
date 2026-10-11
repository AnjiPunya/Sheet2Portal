import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchRecordDetail } from '../api/portal'
import type { RecordItem } from '../types/portal'
import { formatCellValue } from '../lib/format'
import { formatLabel } from '../lib/labels'
import { usePortalNav } from './portalContext'

interface Target {
  worksheet: string
  record: RecordItem
}

/** A readable name for a record: its entity's title column (e.g. a task's
 * name) rather than whichever string field happens to come first (often an
 * id column). */
function recordLabel(record: RecordItem, titleColumn: string | null): string {
  if (titleColumn) {
    const titleValue = record.data[titleColumn]
    if (typeof titleValue === 'string' && titleValue.trim() !== '') return titleValue
  }
  const firstString = Object.values(record.data).find((v) => typeof v === 'string' && v.trim() !== '')
  return (firstString as string) ?? record.id
}

export function RecordDetailModal({
  workbookId,
  worksheet,
  record,
  onClose,
}: {
  workbookId: string
  worksheet: string
  record: RecordItem
  onClose: () => void
}) {
  const nav = usePortalNav()
  const [stack, setStack] = useState<Target[]>([{ worksheet, record }])
  const current = stack[stack.length - 1]
  const currentLabel = recordLabel(current.record, nav.titleColumnFor(current.worksheet))

  const query = useQuery({
    queryKey: ['record-detail', workbookId, current.worksheet, current.record.id],
    queryFn: () => fetchRecordDetail(workbookId, current.worksheet, current.record.id),
  })

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 backdrop-blur-[2px] sm:items-center sm:p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={currentLabel}
        className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-slate-100 px-5 pt-4 pb-3 sm:px-6">
          <div className="flex items-start justify-between gap-3">
            <nav className="flex min-w-0 flex-wrap items-center gap-1 text-xs text-slate-500" aria-label="Record trail">
              {stack.map((item, i) => (
                <span key={`${item.worksheet}:${item.record.id}`} className="flex items-center gap-1">
                  {i > 0 && <span className="text-slate-300">/</span>}
                  <button
                    onClick={() => setStack(stack.slice(0, i + 1))}
                    disabled={i === stack.length - 1}
                    className={i === stack.length - 1 ? 'font-medium text-slate-700' : 'hover:text-indigo-600 hover:underline'}
                  >
                    {nav.labelFor(item.worksheet)}
                  </button>
                </span>
              ))}
            </nav>
            <button
              onClick={onClose}
              aria-label="Close"
              className="-mt-1 -mr-1 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            >
              <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
              </svg>
            </button>
          </div>
          <h3 className="mt-1.5 text-lg font-semibold tracking-tight text-slate-900">{currentLabel}</h3>
        </div>

        <div className="overflow-y-auto px-5 py-4 sm:px-6 sm:py-5">
          {query.isLoading && (
            <div className="animate-pulse space-y-3">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-4 rounded bg-slate-100" />
              ))}
            </div>
          )}

          {query.data && (
            <div className="space-y-6">
              <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
                {Object.entries(query.data.data).map(([key, value]) => {
                  const formatted = formatCellValue(value)
                  if (!formatted) return null
                  return (
                    <div key={key} className="min-w-0 border-b border-slate-100 pb-2">
                      <dt className="text-xs font-medium text-slate-500">{formatLabel(key)}</dt>
                      <dd className="mt-0.5 break-words text-sm font-medium text-slate-800">{formatted}</dd>
                    </div>
                  )
                })}
              </dl>

              {query.data.related.length > 0 && (
                <div className="space-y-4">
                  <p className="section-label">Related records</p>
                  {query.data.related.map((group) => (
                    <div key={group.entity + group.relationship} className="rounded-xl border border-slate-200">
                      <div className="flex items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/70 px-3 py-2">
                        <span className="text-sm font-medium text-slate-700">
                          {nav.labelFor(group.entity)}{' '}
                          <span className="font-normal text-slate-400">({group.records.length})</span>
                        </span>
                        <button
                          onClick={() => {
                            nav.openRelated(group.entity, {
                              worksheet: current.worksheet,
                              recordId: current.record.id,
                              label: currentLabel,
                            })
                            onClose()
                          }}
                          className="text-xs font-medium text-indigo-600 hover:text-indigo-700 hover:underline"
                        >
                          View all →
                        </button>
                      </div>
                      <ul className="divide-y divide-slate-100">
                        {group.records.slice(0, 5).map((related) => (
                          <li key={related.id}>
                            <button
                              onClick={() => setStack([...stack, { worksheet: group.entity, record: related }])}
                              className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
                            >
                              <span className="truncate">{recordLabel(related, nav.titleColumnFor(group.entity))}</span>
                              <span className="text-slate-300" aria-hidden>
                                ›
                              </span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
