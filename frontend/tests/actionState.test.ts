import { test } from 'node:test'
import assert from 'node:assert/strict'
import { actionTitle, changedData, formatActionValue, nextActionState, pendingFrom } from '../src/lib/actionState.ts'
import type { ActionState } from '../src/types/actions.ts'

function state(overrides: Partial<ActionState>): ActionState {
  return {
    state: 'awaiting_confirmation',
    draft_id: 'd1',
    token: 't1',
    expires_at: null,
    preview: {
      action: 'create',
      worksheet: 'Projects',
      entity_label: 'Project',
      record_id: null,
      record_label: 'Green Valley Apartments',
      fields: [],
      status_change: null,
      consequences: [],
      comment: null,
    },
    missing: [],
    errors: {},
    candidates: [],
    code: null,
    message: null,
    ...overrides,
  }
}

test('only an awaiting-confirmation draft with a token can be confirmed by a "yes"', () => {
  assert.deepEqual(pendingFrom(state({})), { draft_id: 'd1', token: 't1' })
  for (const s of ['clarification_required', 'completed', 'cancelled', 'failed'] as const) {
    assert.equal(pendingFrom(state({ state: s })), null, s)
  }
  assert.equal(pendingFrom(state({ token: null })), null)
  assert.equal(pendingFrom(null), null)
})

test('a normal reply keeps the draft on screen; any action state replaces it', () => {
  const draft = state({})
  assert.equal(nextActionState(draft, null), draft)
  assert.equal(nextActionState(draft, undefined), draft)
  const corrected = state({ draft_id: 'd2', token: 't2' })
  assert.equal(nextActionState(draft, corrected), corrected)
  const needsMore = state({ state: 'clarification_required', draft_id: null, token: null })
  // A correction that needs more details drops the old token: "yes" can't confirm stale content.
  assert.equal(pendingFrom(nextActionState(draft, needsMore)), null)
})

test('the portal refreshes only after a completed action', () => {
  assert.equal(changedData(state({ state: 'completed' })), true)
  for (const s of ['awaiting_confirmation', 'clarification_required', 'cancelled', 'failed'] as const) {
    assert.equal(changedData(state({ state: s })), false, s)
  }
  assert.equal(changedData(null), false)
})

test('titles and values read naturally', () => {
  assert.equal(actionTitle(state({})), 'Create project')
  const approve = state({ preview: { ...state({}).preview!, action: 'approve', entity_label: 'Purchase Request', record_label: 'PR-1004' } })
  assert.equal(actionTitle(approve), 'Approve purchase request PR-1004')
  assert.equal(formatActionValue(50000000), '50,000,000')
  assert.equal(formatActionValue(null), '—')
  assert.equal(formatActionValue(true), 'Yes')
})
