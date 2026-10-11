import { test } from 'node:test'
import assert from 'node:assert/strict'
import { categoryColors, statusTone, TONES, CATEGORICAL } from '../src/lib/chartFormat.ts'
import { alertText } from '../src/lib/alerts.ts'

test('statuses are coloured by meaning', () => {
  const cases: [string, string][] = [
    ['Completed', 'done'], ['Done', 'done'], ['Paid', 'done'], ['Resolved', 'done'], ['Approved', 'done'],
    ['In Progress', 'progress'], ['Investigating', 'progress'], ['Monitoring', 'progress'], ['Active', 'progress'],
    ['Open', 'waiting'], ['Pending', 'waiting'], ['Not Started', 'waiting'], ['Pending Approval', 'waiting'],
    ['Follow-up due', 'attention'],
    ['At Risk', 'risk'], ['Overdue', 'risk'], ['Rejected', 'risk'], ['Blocked', 'risk'],
    ['Cancelled', 'neutral'], ['On Hold', 'neutral'], ['Inactive', 'neutral'],
  ]
  for (const [label, tone] of cases) assert.equal(statusTone(label), tone, label)
})

test('different statuses in one chart get different colours', () => {
  for (const labels of [
    ['Not Started', 'In Progress', 'Completed', 'At Risk'],
    ['Open', 'Investigating'],
    ['Open', 'Monitoring', 'Follow-up due'],
    ['Delivered', 'Pending', 'Shipped', 'Cancelled'],
  ]) {
    const colors = categoryColors(labels).map((c) => c.color)
    assert.equal(new Set(colors).size, labels.length, labels.join(', '))
  }
})

test('every status colour ships with an icon (never colour alone)', () => {
  for (const tone of Object.values(TONES)) assert.ok(tone.icon && tone.meaning)
})

test('plain categories use the categorical palette in fixed order', () => {
  const colors = categoryColors(['Accessories', 'Displays', 'Cables'])
  assert.deepEqual(colors.map((c) => c.color), [CATEGORICAL[0], CATEGORICAL[1], CATEGORICAL[2]])
  assert.ok(colors.every((c) => c.tone === null))
})

test('status alerts name their sheet; self-describing alerts do not', () => {
  assert.equal(alertText({ key: 'Expenses_Payments:status:Pending', label: 'Pending' }, 'Expenses Payments'), 'Pending · Expenses Payments')
  assert.equal(alertText({ key: 'Feed_Inventory:low_stock', label: 'Low-Stock Alerts' }, 'Feed Inventory'), 'Low-Stock Alerts')
})

test('workbook status wording is kept in alerts', () => {
  assert.equal(alertText({ key: 'Treatments:status:Follow-up due', label: 'Follow-up due' }, 'Treatments Health'), 'Follow-up due · Treatments Health')
})
