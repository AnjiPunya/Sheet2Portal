import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchRecordDetail } from '../api/portal'
import { decideRecord, deleteRecord, fetchEntitySchema, fetchRecordActivity, updateRecord } from '../api/records'
import { ApiRequestError } from '../api/client'
import type { RecordItem } from '../types/portal'
import type { DecisionAction, EntitySchema, RecordActions, RecordEvent } from '../types/records'
import { formatCellValue, formatFieldValue } from '../lib/format'
import { formatLabel } from '../lib/labels'
import { invalidateWorkbookData } from '../lib/invalidate'
import { usePortalNav } from './portalContext'
import { ConfirmDialog } from './ConfirmDialog'
import { RecordFormDialog } from './RecordFormDialog'
import { StatusBadge } from './StatusBadge'
import { useToast } from './toastContext'

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
  return (firstString as string) ?? 'Record' // never fall back to the internal id
}

const errorMessage = (error: unknown) => (error instanceof ApiRequestError ? error.message : error ? 'Something went wrong.' : null)

export function RecordDetailModal({
  workbookId,
  worksheet,
  record,
  initialLabel,
  onClose,
}: {
  workbookId: string
  worksheet: string
  record: RecordItem
  /** Name to show until the record loads (e.g. from a chat link). */
  initialLabel?: string
  onClose: () => void
}) {
  const nav = usePortalNav()
  const [stack, setStack] = useState<Target[]>([{ worksheet, record }])
  // While a confirmation or edit dialog is open, Escape belongs to it.
  const [childOpen, setChildOpen] = useState(false)
  const current = stack[stack.length - 1]

  const query = useQuery({
    queryKey: ['record-detail', workbookId, current.worksheet, current.record.id],
    queryFn: () => fetchRecordDetail(workbookId, current.worksheet, current.record.id),
  })
  const activity = useQuery({
    queryKey: ['record-activity', workbookId, current.worksheet, current.record.id],
    queryFn: () => fetchRecordActivity(workbookId, current.worksheet, current.record.id),
  })
  const schema = useQuery({
    queryKey: ['entity-schema', workbookId, current.worksheet],
    queryFn: () => fetchEntitySchema(workbookId, current.worksheet),
  })

  const liveRecord: RecordItem = query.data ? { id: query.data.id, data: query.data.data } : current.record
  const currentLabel =
    !query.data && stack.length === 1 && initialLabel ? initialLabel : recordLabel(liveRecord, nav.titleColumnFor(current.worksheet))

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !childOpen && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, childOpen])

  function afterDelete() {
    if (stack.length > 1) setStack(stack.slice(0, -1))
    else onClose()
  }

  const workflow = schema.data?.workflow
  const status = workflow ? formatCellValue(liveRecord.data[workflow.status_column]) : null

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 backdrop-blur-[2px] sm:items-center sm:p-6"
      onMouseDown={() => !childOpen && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={currentLabel}
        className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl sm:rounded-2xl"
        onMouseDown={(e) => e.stopPropagation()}
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
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold tracking-tight text-slate-900">{currentLabel}</h3>
            {status && <StatusBadge value={status} isRisk={status === workflow?.rejected} />}
          </div>
          {activity.data && schema.data && (
            <RecordActionBar
              key={current.record.id}
              workbookId={workbookId}
              worksheet={current.worksheet}
              record={liveRecord}
              label={currentLabel}
              schema={schema.data}
              actions={activity.data.actions}
              onChildOpen={setChildOpen}
              onDeleted={afterDelete}
            />
          )}
        </div>

        <div className="overflow-y-auto px-5 py-4 sm:px-6 sm:py-5">
          {query.isError && (
            <p role="alert" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              This record is no longer available -- it may have been deleted. Nothing was opened in its place.
            </p>
          )}

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
                  const formatted = formatFieldValue(value, nav.roleFor(current.worksheet, key))
                  if (!formatted) return null
                  return (
                    <div key={key} className="min-w-0 border-b border-slate-100 pb-2">
                      <dt className="text-xs font-medium text-slate-500">{formatLabel(key)}</dt>
                      <dd className="mt-0.5 break-words text-sm font-medium text-slate-800">
                        {query.data.display?.[key] ? (
                          <>
                            {query.data.display[key]} <span className="text-xs font-normal text-slate-400">{formatted}</span>
                          </>
                        ) : (
                          formatted
                        )}
                      </dd>
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

              {activity.data && activity.data.history.length > 0 && <ActivityTimeline events={activity.data.history} />}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

type Pending =
  | { kind: 'edit' }
  | { kind: 'delete' }
  | { kind: 'decide'; action: DecisionAction }

const DECISION_COPY: Record<DecisionAction, { title: string; confirm: string; tone: 'emerald' | 'red' | 'indigo'; done: string }> = {
  approve: { title: 'Approve this request?', confirm: 'Approve', tone: 'emerald', done: 'Approved' },
  reject: { title: 'Reject this request?', confirm: 'Reject', tone: 'red', done: 'Rejected' },
  resubmit: { title: 'Resubmit for approval?', confirm: 'Resubmit', tone: 'indigo', done: 'Resubmitted for approval' },
}

/** Only the actions the backend says this user may take on this record right
 * now; every one is re-checked on the server. */
function RecordActionBar({
  workbookId,
  worksheet,
  record,
  label,
  schema,
  actions,
  onChildOpen,
  onDeleted,
}: {
  workbookId: string
  worksheet: string
  record: RecordItem
  label: string
  schema: EntitySchema
  actions: RecordActions
  onChildOpen: (open: boolean) => void
  onDeleted: () => void
}) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [pending, setPendingState] = useState<Pending | null>(null)
  const setPending = (next: Pending | null) => {
    setPendingState(next)
    onChildOpen(next !== null)
  }

  const refresh = () => invalidateWorkbookData(queryClient, workbookId)

  const remove = useMutation({
    mutationFn: () => deleteRecord(workbookId, worksheet, record.id),
    onSuccess: () => {
      refresh()
      toast(`${schema.singular_label} deleted`)
      setPending(null)
      onDeleted()
    },
  })
  const decision = useMutation({
    mutationFn: ({ action, comment }: { action: DecisionAction; comment: string }) =>
      decideRecord(workbookId, worksheet, record.id, action, comment),
    onSuccess: (_result, { action }) => {
      refresh()
      toast(DECISION_COPY[action].done)
      setPending(null)
    },
  })
  const statusChange = useMutation({
    mutationFn: (value: string) => updateRecord(workbookId, worksheet, record.id, { [statusField!.name]: value }),
    onSuccess: (_r, value) => {
      refresh()
      toast(`Status set to ${value}`)
    },
    onError: (error) => toast(errorMessage(error) ?? 'Could not update status', 'error'),
  })

  // Quick status updates (tasks, issues...) for entities without an approval workflow.
  const statusField = schema.fields.find((f) => f.role === 'status' && f.input === 'select' && !f.workflow && f.name === statusColumnOf(schema))
  const currentStatus = statusField ? formatCellValue(record.data[statusField.name]) : ''
  const doneStatus = schema.done_statuses.find((s) => s !== currentStatus)
  const isDone = schema.done_statuses.includes(currentStatus)

  const anyAction = actions.edit || actions.delete || actions.approve || actions.reject || actions.resubmit
  if (!anyAction) return null

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      {actions.approve && (
        <button onClick={() => setPending({ kind: 'decide', action: 'approve' })} className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700">
          ✓ Approve
        </button>
      )}
      {actions.reject && (
        <button onClick={() => setPending({ kind: 'decide', action: 'reject' })} className="inline-flex items-center gap-1 rounded-lg bg-white px-3 py-1.5 text-sm font-semibold text-red-700 shadow-sm ring-1 ring-red-200 hover:bg-red-50">
          ✕ Reject
        </button>
      )}
      {actions.resubmit && (
        <button onClick={() => setPending({ kind: 'decide', action: 'resubmit' })} className="btn-secondary">
          ↻ Resubmit
        </button>
      )}
      {actions.edit && statusField && (
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <span className="sr-only">Status</span>
          <select
            value={currentStatus}
            disabled={statusChange.isPending}
            onChange={(e) => e.target.value && statusChange.mutate(e.target.value)}
            className="input py-1.5"
          >
            {!statusField.options?.includes(currentStatus) && <option value={currentStatus}>{currentStatus || 'No status'}</option>}
            {statusField.options?.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </label>
      )}
      {actions.edit && statusField && doneStatus && !isDone && (
        <button onClick={() => statusChange.mutate(doneStatus)} disabled={statusChange.isPending} className="btn-secondary">
          Mark {doneStatus.toLowerCase()}
        </button>
      )}
      {actions.edit && (
        <button onClick={() => setPending({ kind: 'edit' })} className="btn-secondary">
          Edit
        </button>
      )}
      {actions.delete && (
        <button onClick={() => setPending({ kind: 'delete' })} className="ml-auto rounded-lg px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50">
          Delete
        </button>
      )}

      {pending?.kind === 'edit' && (
        <RecordFormDialog workbookId={workbookId} worksheet={worksheet} record={record} onClose={() => setPending(null)} />
      )}
      {pending?.kind === 'delete' && (
        <ConfirmDialog
          title={`Delete this ${schema.singular_label.toLowerCase()}?`}
          message={
            <>
              <strong className="text-slate-800">{label}</strong> will be permanently removed. KPIs and charts update
              straight away. This can't be undone.
            </>
          }
          confirmLabel="Delete"
          tone="red"
          isPending={remove.isPending}
          error={errorMessage(remove.error)}
          onConfirm={() => remove.mutate()}
          onCancel={() => {
            remove.reset()
            setPending(null)
          }}
        />
      )}
      {pending?.kind === 'decide' && (
        <ConfirmDialog
          title={DECISION_COPY[pending.action].title}
          message={
            <>
              <strong className="text-slate-800">{label}</strong>
              {pending.action === 'approve' && ' will be approved and locked from further edits.'}
              {pending.action === 'reject' && ' will be rejected. The requester can revise and resubmit it.'}
              {pending.action === 'resubmit' && ' will go back to pending approval.'}
            </>
          }
          confirmLabel={DECISION_COPY[pending.action].confirm}
          tone={DECISION_COPY[pending.action].tone}
          withComment
          commentLabel={pending.action === 'reject' ? 'Reason (optional)' : 'Comment (optional)'}
          isPending={decision.isPending}
          error={errorMessage(decision.error)}
          onConfirm={(comment) => decision.mutate({ action: pending.action, comment })}
          onCancel={() => {
            decision.reset()
            setPending(null)
          }}
        />
      )}
    </div>
  )
}

function statusColumnOf(schema: EntitySchema): string | undefined {
  return schema.fields.find((f) => f.role === 'status' && f.input === 'select')?.name
}

const EVENT_LABELS: Record<RecordEvent['action'], string> = {
  created: 'Created',
  updated: 'Edited',
  deleted: 'Deleted',
  approved: 'Approved',
  rejected: 'Rejected',
  resubmitted: 'Resubmitted',
}
const EVENT_DOT: Record<RecordEvent['action'], string> = {
  created: 'bg-indigo-500',
  updated: 'bg-slate-400',
  deleted: 'bg-red-500',
  approved: 'bg-emerald-500',
  rejected: 'bg-red-500',
  resubmitted: 'bg-amber-500',
}

function ActivityTimeline({ events }: { events: RecordEvent[] }) {
  return (
    <div className="space-y-3">
      <p className="section-label">Activity</p>
      <ol className="space-y-3 border-l border-slate-200 pl-4">
        {events.map((event) => {
          const changed = event.action === 'updated' ? Object.keys(event.changes) : []
          return (
            <li key={event.id} className="relative text-sm">
              <span className={`absolute top-1.5 -left-[21px] h-2.5 w-2.5 rounded-full ring-2 ring-white ${EVENT_DOT[event.action]}`} aria-hidden />
              <p className="text-slate-700">
                <span className="font-medium text-slate-900">{EVENT_LABELS[event.action]}</span> by {event.user_name}
                {event.to_status && event.action !== 'created' && event.action !== 'updated' && (
                  <span className="text-slate-500">
                    {' '}
                    · {event.from_status} → {event.to_status}
                  </span>
                )}
              </p>
              {changed.length > 0 && <p className="text-xs text-slate-500">Changed {changed.map(formatLabel).join(', ')}</p>}
              {event.comment && <p className="mt-1 rounded-lg bg-slate-50 px-2.5 py-1.5 text-slate-600">“{event.comment}”</p>}
              <time className="text-xs text-slate-400" dateTime={event.created_at}>
                {new Date(event.created_at.endsWith('Z') || event.created_at.includes('+') ? event.created_at : `${event.created_at}Z`).toLocaleString()}
              </time>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
