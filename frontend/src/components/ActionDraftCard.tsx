import { STATE_LABEL, actionTitle, formatActionValue } from '../lib/actionState'
import type { ActionCandidate, ActionState } from '../types/actions'

const TONE: Record<ActionState['state'], string> = {
  clarification_required: 'border-amber-200 bg-amber-50',
  awaiting_confirmation: 'border-indigo-200 bg-indigo-50/60',
  completed: 'border-emerald-200 bg-emerald-50',
  cancelled: 'border-slate-200 bg-slate-50',
  failed: 'border-red-200 bg-red-50',
}

const BADGE: Record<ActionState['state'], string> = {
  clarification_required: 'bg-amber-100 text-amber-800',
  awaiting_confirmation: 'bg-indigo-100 text-indigo-700',
  completed: 'bg-emerald-100 text-emerald-700',
  cancelled: 'bg-slate-200 text-slate-600',
  failed: 'bg-red-100 text-red-700',
}

/**
 * The assistant's draft for a business action. Nothing is changed until the
 * user confirms here (or says "yes"); the server re-checks everything then.
 */
export function ActionDraftCard({
  action,
  busy,
  onConfirm,
  onCancel,
  onChoose,
}: {
  action: ActionState
  busy: boolean
  onConfirm: () => void
  onCancel: () => void
  onChoose: (candidate: ActionCandidate) => void
}) {
  const preview = action.preview
  const destructive = preview?.action === 'delete'
  const awaiting = action.state === 'awaiting_confirmation'

  return (
    <section aria-label="Action draft" className={`rounded-xl border px-3 py-2.5 text-xs ${TONE[action.state]}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="min-w-0 truncate font-semibold text-slate-800" title={actionTitle(action)}>
          {actionTitle(action)}
        </p>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${BADGE[action.state]}`}>{STATE_LABEL[action.state]}</span>
      </div>

      {preview && preview.fields.length > 0 && action.state !== 'cancelled' && (
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
          {preview.fields.map((f) => (
            <div key={f.name} className="contents">
              <dt className="text-slate-500">{f.label}</dt>
              <dd className="min-w-0 break-words text-slate-800">
                {f.previous !== undefined && (
                  <>
                    <span className="text-slate-400 line-through">{formatActionValue(f.previous)}</span>
                    <span aria-hidden> → </span>
                  </>
                )}
                <span className="font-medium">{formatActionValue(f.value)}</span>
                {f.computed && <span className="ml-1 text-[10px] uppercase tracking-wide text-slate-400">calculated</span>}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {preview?.status_change && (
        <p className="mt-2 text-slate-700">
          Status: <span className="text-slate-500">{preview.status_change.from}</span> → <span className="font-medium">{preview.status_change.to}</span>
          {preview.comment && <span className="block text-slate-500">Comment: {preview.comment}</span>}
        </p>
      )}

      {preview && preview.consequences.length > 0 && awaiting && (
        <ul className={`mt-2 space-y-0.5 ${destructive ? 'font-medium text-red-700' : 'text-slate-600'}`}>
          {preview.consequences.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      )}

      {action.state === 'clarification_required' && action.missing.length > 0 && (
        <p className="mt-2 text-amber-800">Still needed: {action.missing.map((m) => m.label).join(', ')}</p>
      )}
      {Object.keys(action.errors).length > 0 && action.state !== 'completed' && (
        <ul className="mt-2 space-y-0.5 text-red-700">
          {Object.entries(action.errors).map(([field, message]) => (
            <li key={field}>
              {field}: {message}
            </li>
          ))}
        </ul>
      )}
      {action.message && action.state !== 'completed' && <p className="mt-2 text-slate-700">{action.message}</p>}

      {action.candidates.length > 0 && (
        <div className="mt-2 flex flex-col gap-1">
          {action.candidates.map((c) => (
            <button
              key={c.record_id}
              type="button"
              disabled={busy}
              onClick={() => onChoose(c)}
              className="rounded-lg border border-amber-200 bg-white px-2 py-1 text-left text-slate-700 hover:border-amber-400 disabled:opacity-50"
            >
              {c.label}
              {c.status && <span className="ml-1 text-slate-400">· {c.status}</span>}
            </button>
          ))}
        </div>
      )}

      {awaiting && (
        <div className="mt-2.5 flex items-center gap-2">
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`rounded-lg px-3 py-1.5 font-medium text-white disabled:opacity-50 ${
              destructive ? 'bg-red-600 hover:bg-red-700' : 'bg-indigo-600 hover:bg-indigo-700'
            }`}
          >
            {destructive ? 'Delete' : 'Confirm'}
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-lg px-3 py-1.5 font-medium text-slate-600 hover:bg-white disabled:opacity-50"
          >
            Cancel
          </button>
          <span className="ml-auto text-[11px] text-slate-400">or say “yes” / “అవును”</span>
        </div>
      )}
    </section>
  )
}
