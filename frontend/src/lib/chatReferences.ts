import type { ChatReference, ChatReferenceAction } from '../types/chat.ts'

/** What a reference chip says: the record's name -- never an internal id or a
 * "#cc8957" fragment. Without a resolved name it falls back to the record type. */
export function referenceTitle(ref: ChatReference, sheetLabel: string): string {
  if (ref.label && ref.label.trim()) return ref.label
  return `${ref.entity_label ?? sheetLabel} record`
}

/** Related-record actions to offer ("View Tasks"...), most useful first, capped. */
export function relatedActions(ref: ChatReference, limit = 6): ChatReferenceAction[] {
  return (ref.actions ?? []).filter((a) => a.kind === 'related' && (a.count ?? 1) > 0).slice(0, limit)
}
