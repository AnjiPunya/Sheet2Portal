import { test } from 'node:test'
import assert from 'node:assert/strict'
import { formatLabel } from '../src/lib/labels.ts'

const CASES: [string, string][] = [
  ['Project_Manager', 'Project Manager'],
  ['project_manager', 'Project Manager'],
  ['purchase-requests', 'Purchase Requests'],
  ['projectName', 'Project Name'],
  ['PR_ID', 'PR ID'],
  ['PR ID', 'PR ID'],
  ['SKU_code', 'SKU Code'],
  ['PURCHASE_REQUESTS', 'Purchase Requests'],
  ['Project__Manager ', 'Project Manager'],
  ['Project Manager', 'Project Manager'],
]

// Same table as backend/tests/test_labels_and_related_filter.py::test_humanize,
// so server- and client-formatted labels can't drift apart.
for (const [raw, expected] of CASES) {
  test(`formatLabel(${JSON.stringify(raw)}) -> ${JSON.stringify(expected)}`, () => {
    assert.equal(formatLabel(raw), expected)
  })
}

test('formatLabel is idempotent', () => {
  for (const raw of ['Project_Manager', 'PR_ID', 'unitCost', 'PURCHASE_REQUESTS']) {
    assert.equal(formatLabel(formatLabel(raw)), formatLabel(raw))
  }
})

test('formatLabel never leaves underscores', () => {
  for (const raw of ['a_b_c', '__lead', 'trail__', 'Mixed_Case_NAME']) {
    assert.ok(!formatLabel(raw).includes('_'), raw)
  }
})
