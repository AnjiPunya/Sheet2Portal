import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  clearRelatedFilter,
  entityPageKey,
  entityView,
  navKey,
  relatedEntityView,
  type RelatedFilter,
} from '../src/lib/portalView.ts'
import { buildRecordParams } from '../src/lib/recordQuery.ts'

const lakeview: RelatedFilter = { worksheet: 'Projects', recordId: 'p-lakeview', label: 'Lakeview Luxury Villas' }
const orchid: RelatedFilter = { worksheet: 'Projects', recordId: 'p-orchid', label: 'Orchid Commercial Fit-out' }

test('"View all" keeps the parent record id in the view', () => {
  const view = relatedEntityView('Tasks', lakeview)
  assert.equal(view.worksheet, 'Tasks')
  assert.deepEqual(view.related, lakeview)
})

test('related view sends only parent worksheet + id to the records API', () => {
  const params = buildRecordParams({ related: relatedEntityView('Tasks', lakeview).related, page: 2, pageSize: 24 })
  assert.equal(params.get('related_worksheet'), 'Projects')
  assert.equal(params.get('related_record_id'), 'p-lakeview')
  assert.equal(params.get('page'), '2')
  assert.equal(params.get('page_size'), '24')
})

test('related filter combines with search and status', () => {
  const params = buildRecordParams({ related: lakeview, search: 'mep', status: 'Open' })
  assert.equal(params.get('search'), 'mep')
  assert.equal(params.get('status'), 'Open')
  assert.equal(params.get('related_record_id'), 'p-lakeview')
})

test('clearing the filter removes it from the view and the request', () => {
  const cleared = clearRelatedFilter(relatedEntityView('Tasks', lakeview))
  assert.deepEqual(cleared, { worksheet: 'Tasks' })
  const params = buildRecordParams({ related: cleared.related })
  assert.equal(params.has('related_worksheet'), false)
  assert.equal(params.has('related_record_id'), false)
})

test('plain tab navigation never carries a filter', () => {
  assert.deepEqual(entityView('Tasks'), { worksheet: 'Tasks' })
})

test('filtered and unfiltered views share a nav tab', () => {
  assert.equal(navKey(relatedEntityView('Tasks', lakeview)), navKey(entityView('Tasks')))
})

test('page key changes per parent so paging/search state resets', () => {
  const keys = new Set([
    entityPageKey(entityView('Tasks')),
    entityPageKey(relatedEntityView('Tasks', lakeview)),
    entityPageKey(relatedEntityView('Tasks', orchid)),
  ])
  assert.equal(keys.size, 3)
})

test('the stored filter is a copy, not the caller object', () => {
  const parent = { ...lakeview }
  const view = relatedEntityView('Tasks', parent)
  parent.recordId = 'mutated'
  assert.equal(view.related?.recordId, 'p-lakeview')
})
