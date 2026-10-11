import { test } from 'node:test'
import assert from 'node:assert/strict'
import { referenceTitle, relatedActions } from '../src/lib/chatReferences.ts'
import type { ChatReference } from '../src/types/chat.ts'

const project: ChatReference = {
  worksheet: 'Projects',
  record_id: 'cc8957a1-0000-4000-8000-000000000001',
  label: 'Green Meadows Apartments',
  entity_label: 'Project',
  actions: [
    { kind: 'details', label: 'View details', worksheet: 'Projects' },
    { kind: 'related', label: 'View Tasks', worksheet: 'Tasks', count: 5 },
    { kind: 'related', label: 'View Materials', worksheet: 'Materials', count: 6 },
    { kind: 'related', label: 'View Expenses Payments', worksheet: 'Expenses_Payments', count: 5 },
    { kind: 'related', label: 'View Daily Progress', worksheet: 'Daily_Progress', count: 4 },
    { kind: 'related', label: 'View Empty', worksheet: 'Empty', count: 0 },
  ],
}

test('chips show the record name, never an id fragment', () => {
  assert.equal(referenceTitle(project, 'Projects'), 'Green Meadows Apartments')
  const unnamed: ChatReference = { worksheet: 'Projects', record_id: project.record_id, entity_label: 'Project' }
  assert.equal(referenceTitle(unnamed, 'Projects'), 'Project record')
  assert.ok(!referenceTitle(unnamed, 'Projects').includes('#'))
  assert.ok(!referenceTitle(unnamed, 'Projects').includes('cc8957'))
})

test('related actions: tasks, materials, expenses, progress logs; none for empty sheets', () => {
  const labels = relatedActions(project).map((a) => a.label)
  assert.deepEqual(labels, ['View Tasks', 'View Materials', 'View Expenses Payments', 'View Daily Progress'])
  assert.equal(relatedActions(project, 2).length, 2)
})
