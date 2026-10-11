import type { ChatReference } from '../types/chat'
import { referenceTitle, relatedActions } from '../lib/chatReferences'
import { usePortalNav } from './portalContext'

/** Records the answer used, by name. Clicking a name opens that exact record
 * (by its real id); "View Tasks"-style actions open the related records,
 * filtered to this one. Every action goes through the normal, permission-
 * checked API for this workbook. */
export function ChatReferences({ references }: { references: ChatReference[] }) {
  const nav = usePortalNav()
  const showActions = references.length <= 4

  return (
    <div className="mt-2 space-y-1.5 border-t border-slate-200 pt-2">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Records used</p>
      <ul className="flex flex-col gap-1.5">
        {references.map((ref) => {
          const title = referenceTitle(ref, nav.labelFor(ref.worksheet))
          const related = showActions ? relatedActions(ref) : []
          return (
            <li key={`${ref.worksheet}-${ref.record_id}`} className="rounded-lg bg-white px-2 py-1.5 ring-1 ring-slate-200">
              <button
                onClick={() => nav.openRecord(ref.worksheet, ref.record_id, title)}
                className="flex w-full items-baseline justify-between gap-2 text-left"
                title={`View details of ${title}`}
              >
                <span className="truncate text-xs font-semibold text-indigo-700 hover:underline">{title}</span>
                <span className="shrink-0 text-[10px] text-slate-400">{ref.entity_label ?? nav.labelFor(ref.worksheet)}</span>
              </button>
              {(showActions || related.length > 0) && (
                <div className="mt-1 flex flex-wrap gap-1">
                  <button
                    onClick={() => nav.openRecord(ref.worksheet, ref.record_id, title)}
                    className="rounded-full px-2 py-0.5 text-[11px] font-medium text-indigo-600 ring-1 ring-indigo-200 hover:bg-indigo-50"
                  >
                    View details
                  </button>
                  {related.map((action) => (
                    <button
                      key={action.worksheet}
                      onClick={() => nav.openRelated(action.worksheet, { worksheet: ref.worksheet, recordId: ref.record_id, label: title })}
                      className="rounded-full px-2 py-0.5 text-[11px] font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
                    >
                      {action.label}
                      {action.count ? <span className="ml-1 text-slate-400">{action.count}</span> : null}
                    </button>
                  ))}
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
