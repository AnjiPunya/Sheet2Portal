import { test } from 'node:test'
import assert from 'node:assert/strict'
import { formatFieldValue } from '../src/lib/format.ts'

test('amounts and quantities get thousands separators', () => {
  assert.equal(formatFieldValue(210000, 'amount'), '210,000')
  assert.equal(formatFieldValue(1228500.5, 'actual_amount'), '1,228,500.5')
  assert.equal(formatFieldValue(4200, 'quantity'), '4,200')
})

test('identifiers, phone numbers and other numbers are shown as entered', () => {
  assert.equal(formatFieldValue(9000000101, 'other'), '9000000101')
  assert.equal(formatFieldValue(2026, null), '2026')
  assert.equal(formatFieldValue('POND-001', 'identifier'), 'POND-001')
  assert.equal(formatFieldValue(true, 'flag'), 'Yes')
  assert.equal(formatFieldValue(null, 'amount'), '')
})
