import { test } from 'node:test'
import assert from 'node:assert/strict'
import { formatCompact, formatPercent, formatPeriod, niceTicks } from '../src/lib/chartFormat.ts'

test('axis ticks start at zero, are evenly stepped, and cover the maximum', () => {
  for (const max of [7, 100, 2_520_000, 49_700_000, 0.4]) {
    const ticks = niceTicks(max)
    assert.equal(ticks[0], 0)
    assert.ok(ticks[ticks.length - 1] >= max, `${max}: ${ticks}`)
    const steps = new Set(ticks.slice(1).map((t, i) => Math.round((t - ticks[i]) * 1e6)))
    assert.equal(steps.size, 1, `uneven steps for ${max}: ${ticks}`)
  }
  assert.deepEqual(niceTicks(0), [0])
})

test('compact numbers from 1,000 up', () => {
  assert.equal(formatCompact(999), '999')
  assert.equal(formatCompact(2_520_000), '2.5M')
  assert.equal(formatCompact(49_700_000), '49.7M')
})

test('percent of a whole, safe for empty totals', () => {
  assert.equal(formatPercent(1, 6), '17%')
  assert.equal(formatPercent(0, 0), '0%')
})

test('period labels per bucket size', () => {
  assert.equal(formatPeriod('2026-09-21', 'week'), 'Wk of 21 Sep')
  assert.equal(formatPeriod('2026-09-21', 'day'), '21 Sep')
  assert.equal(formatPeriod('2026-02-01', 'month'), 'Feb 2026')
  assert.equal(formatPeriod('2026-07-01', 'quarter'), 'Q3 2026')
})
