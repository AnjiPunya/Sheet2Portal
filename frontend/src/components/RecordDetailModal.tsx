import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchRecordDetail } from '../api/portal'
import type { RecordItem } from '../types/portal'
import { formatCellValue } from '../lib/format'

interface Target {
  worksheet: string
  record: RecordItem
}

function recordLabel(record: RecordItem, worksheet: string, titleColumnByWorksheet: Record<string, string | null>): string {
  const titleColumn = titleColumnByWorksheet[worksheet]
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
  titleColumnByWorksheet,
  onClose,
  onNavigateEntity,
}: {
  workbookId: string
  worksheet: string
  record: RecordItem
  /** worksheet -> its entity's title_column, so related records show a
   * readable name (e.g. a task's title) instead of whichever string field
   * happens to come first (often an id column). */
  titleColumnByWorksheet: Record<string, string | null>
  onClose: () => void
  onNavigateEntity: (worksheet: string) => void
}) {
  const [stack, setStack] = useState<Target[]>([{ worksheet, record }])
  const current = stack[stack.length - 1]

  const query = useQuery({
    queryKey: ['record-detail', workbookId, current.worksheet, current.record.id],
    queryFn: () => fetchRecordDetail(workbookId, current.worksheet, current.record.id),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <div
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1 text-sm text-slate-400">
            {stack.map((item, i) => (
              <span key={item.record.id} className="flex items-center gap-1">
                {i > 0 && <span>/</span>}
                <button
                  onClick={() => setStack(stack.slice(0, i + 1))}
                  className={i === stack.length - 1 ? 'font-medium text-slate-700' : 'hover:underline'}
                >
                  {item.worksheet}
                </button>
              </span>
            ))}
          </div>
          <button onClick={onClose} aria-label="Close" className="text-slate-400 hover:text-slate-600">
            <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>

        {query.isLoading && <p className="text-sm text-slate-400">Loading…</p>}

        {query.data && (
          <div className="space-y-5">
            <div className="space-y-2">
              {Object.entries(query.data.data).map(([key, value]) => {
                const formatted = formatCellValue(value)
                if (!formatted) return null
                return (
                  <div key={key} className="flex justify-between gap-4 border-b border-slate-100 pb-1 text-sm">
                    <span className="text-slate-400">{key}</span>
                    <span className="text-right font-medium text-slate-700">{formatted}</span>
                  </div>
                )
              })}
            </div>

            {query.data.related.length > 0 && (
              <div className="space-y-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Related</p>
                {query.data.related.map((group) => (
                  <div key={group.entity + group.relationship}>
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-sm font-medium text-slate-600">{group.entity}</span>
                      <button
                        onClick={() => {
                          onNavigateEntity(group.entity)
                          onClose()
                        }}
                        className="text-xs text-indigo-600 hover:underline"
                      >
                        View all
                      </button>
                    </div>
                    <div className="flex flex-col gap-1">
                      {group.records.slice(0, 5).map((related) => (
                        <button
                          key={related.id}
                          onClick={() => setStack([...stack, { worksheet: group.entity, record: related }])}
                          className="rounded-lg border border-slate-100 px-3 py-1.5 text-left text-sm text-slate-600 hover:bg-slate-50"
                        >
                          {recordLabel(related, group.entity, titleColumnByWorksheet)}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
