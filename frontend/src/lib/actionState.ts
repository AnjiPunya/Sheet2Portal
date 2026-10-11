// Pure helpers for the assistant's business-action drafts (no React), so the
// client-side rules can be unit-tested with `node --test`.

import type { ActionState, PendingAction } from '../types/actions.ts'

/**
 * The draft a reply leaves on screen. A reply without an `action` (a normal
 * question) keeps the current one; any action state replaces it -- only an
 * awaiting-confirmation draft carries a token that a "yes" may confirm.
 */
export function nextActionState(current: ActionState | null, incoming: ActionState | null | undefined): ActionState | null {
  return incoming === undefined || incoming === null ? current : incoming
}

export function pendingFrom(state: ActionState | null): PendingAction | null {
  if (!state || state.state !== 'awaiting_confirmation' || !state.draft_id || !state.token) return null
  return { draft_id: state.draft_id, token: state.token }
}

/** True when a reply means workbook data changed and the portal should refetch. */
export function changedData(state: ActionState | null | undefined): boolean {
  return state?.state === 'completed'
}

const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })

export function formatActionValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'number') return number.format(value)
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

const VERBS: Record<string, string> = {
  create: 'Create',
  update: 'Update',
  delete: 'Delete',
  approve: 'Approve',
  reject: 'Reject',
  resubmit: 'Resubmit',
}

export function actionTitle(state: ActionState): string {
  const preview = state.preview
  if (!preview) return state.state === 'cancelled' ? 'Action cancelled' : 'Action'
  const verb = VERBS[preview.action] ?? preview.action
  const target = preview.action === 'create' ? preview.entity_label.toLowerCase() : `${preview.entity_label.toLowerCase()} ${preview.record_label}`
  return `${verb} ${target}`.trim()
}

export const STATE_LABEL: Record<ActionState['state'], string> = {
  clarification_required: 'Needs details',
  awaiting_confirmation: 'Awaiting your confirmation',
  completed: 'Done',
  cancelled: 'Cancelled',
  failed: 'Not done',
}
