import { test } from 'node:test'
import assert from 'node:assert/strict'
import { applyChange, buildPayload, initialValues, previewComputed, validateForm } from '../src/lib/recordForm.ts'
import type { EntitySchema, FieldSpec } from '../src/types/records.ts'

function field(overrides: Partial<FieldSpec> & Pick<FieldSpec, 'name'>): FieldSpec {
  return {
    label: overrides.name,
    type: 'string',
    input: 'text',
    role: 'other',
    required: false,
    readonly: false,
    computed: null,
    options: null,
    suggestions: null,
    min: null,
    auto: null,
    ...overrides,
  }
}

// Mirrors the construction demo's Purchase Requests schema.
const schema: EntitySchema = {
  worksheet: 'Purchase Requests',
  label: 'Purchase Requests',
  singular_label: 'Purchase Request',
  identifier_column: 'PR ID',
  title_column: 'Item',
  can_create: true,
  done_statuses: [],
  workflow: { status_column: 'Status', pending: 'Pending Approval', approved: 'Approved', rejected: 'Rejected' },
  formulas: [
    {
      target: 'Amount',
      factors: [
        { column: 'Quantity', lookup_from: null },
        { column: 'Unit Cost', lookup_from: 'Item' },
      ],
      description: 'Amount = Quantity × Unit Cost (from Materials)',
    },
  ],
  fields: [
    field({ name: 'PR ID', auto: 'next_id', placeholder: 'PR-1007' }),
    field({ name: 'Item', input: 'select', required: true, options: ['TMT Steel Bars 12mm', 'Red Clay Bricks'] }),
    field({
      name: 'Unit Cost',
      type: 'float',
      input: 'number',
      required: true,
      min: 0,
      lookup: { from: 'Item', entity: 'Materials', defaults: { 'TMT Steel Bars 12mm': 42000, 'Red Clay Bricks': 8 } },
    }),
    field({ name: 'Quantity', type: 'int', input: 'number', required: true, min: 0 }),
    field({ name: 'Requested Date', type: 'date', input: 'date', required: true }),
    field({ name: 'Status', input: 'select', readonly: true, workflow: true, default: 'Pending Approval', options: ['Pending Approval'] }),
    field({ name: 'Amount', type: 'int', input: 'number', readonly: true, computed: 'Amount = Quantity × Unit Cost' }),
  ],
}

test('new records start from defaults; edits start from the record', () => {
  assert.equal(initialValues(schema).Status, 'Pending Approval')
  assert.equal(initialValues(schema).Quantity, '')
  const editing = initialValues(schema, { Item: 'Red Clay Bricks', Quantity: 10, Amount: 80 })
  assert.equal(editing.Quantity, '10')
  assert.equal(editing.Item, 'Red Clay Bricks')
})

test('choosing an item prefills its unit cost from the lookup', () => {
  const next = applyChange(schema, initialValues(schema), 'Item', 'TMT Steel Bars 12mm', new Set())
  assert.equal(next['Unit Cost'], '42000')
})

test('a unit cost the user typed is not overwritten by a later item change', () => {
  const touched = new Set(['Unit Cost'])
  const values = { ...initialValues(schema), 'Unit Cost': '40000' }
  assert.equal(applyChange(schema, values, 'Item', 'Red Clay Bricks', touched)['Unit Cost'], '40000')
})

test('total is previewed live with the same formula as the backend', () => {
  const values = { ...initialValues(schema), Quantity: '5', 'Unit Cost': '42000' }
  assert.deepEqual(previewComputed(schema, values), { Amount: 210000 })
  assert.deepEqual(previewComputed(schema, { ...values, Quantity: '' }), { Amount: null })
})

test('required, number, whole-number, minimum, date and option checks', () => {
  const errors = validateForm(schema, {
    ...initialValues(schema),
    Item: 'Gold',
    'Unit Cost': '-1',
    Quantity: '2.5',
    'Requested Date': '11/10/2026',
  })
  assert.equal(errors.Item, 'Choose one of the options.')
  assert.equal(errors['Unit Cost'], 'Must be zero or more.')
  assert.equal(errors.Quantity, 'Enter a whole number.')
  assert.match(errors['Requested Date'], /valid date/)
  assert.equal(validateForm(schema, initialValues(schema)).Quantity, 'Quantity is required.')
})

test('auto IDs, workflow status and calculated fields are never required or sent', () => {
  const values = { ...initialValues(schema), Item: 'Red Clay Bricks', 'Unit Cost': '8', Quantity: '3', 'Requested Date': '2026-10-11' }
  assert.deepEqual(validateForm(schema, values), {})
  const payload = buildPayload(schema, values)
  assert.deepEqual(payload, { Item: 'Red Clay Bricks', 'Unit Cost': 8, Quantity: 3, 'Requested Date': '2026-10-11' })
})

test('edits send only changed fields, and a cleared field as null', () => {
  const original = initialValues(schema, { Item: 'Red Clay Bricks', Quantity: 10, 'Requested Date': '2026-10-01', 'Unit Cost': 8 })
  assert.deepEqual(buildPayload(schema, { ...original, Quantity: '12' }, original), { Quantity: 12 })
  assert.deepEqual(buildPayload(schema, { ...original, 'Requested Date': '' }, original), { 'Requested Date': null })
})

test('an untouched blank field in an existing record does not block saving', () => {
  const original = initialValues(schema, { Item: 'Red Clay Bricks', Quantity: 10, 'Unit Cost': 8 })
  assert.equal(validateForm(schema, original, original)['Requested Date'], undefined)
  assert.equal(validateForm(schema, { ...original, Quantity: '' }, original).Quantity, 'Quantity is required.')
})

// --- business rules mirrored in the browser ---------------------------------

const rulesSchema: EntitySchema = {
  ...schema,
  workflow: null,
  formulas: [],
  fields: [
    field({ name: 'Feed_Item_ID', input: 'select', required: true, options: ['FEED-002', 'FEED-003'], option_labels: { 'FEED-002': 'FEED-002 · Grower' } }),
    field({ name: 'Quantity_Kg', type: 'int', input: 'number', required: true, min: 0, max_from: { from: 'Feed_Item_ID', entity: 'Feed_Inventory', available: { 'FEED-002': 620, 'FEED-003': 400 } } }),
    field({ name: 'Opening_Stock', type: 'int', input: 'number', min: 0 }),
    field({ name: 'Received_Qty', type: 'int', input: 'number', min: 0 }),
    field({ name: 'Used_Qty', label: 'Used QTY', type: 'int', input: 'number', min: 0, max_sum: ['Opening_Stock', 'Received_Qty'] }),
    field({ name: 'Progress_Percent', type: 'int', input: 'number', min: 0, max: 100 }),
    field({ name: 'Rating', type: 'float', input: 'number', min: 0, max: 5 }),
    field({ name: 'Start_Date', label: 'Start Date', type: 'date', input: 'date' }),
    field({ name: 'Due_Date', label: 'Due Date', type: 'date', input: 'date', after: 'Start_Date' }),
    field({ name: 'Email', input: 'email', format: 'email' }),
    field({ name: 'Phone', input: 'tel', format: 'tel' }),
    field({ name: 'Reading_Time', input: 'time', format: 'time' }),
  ],
}
const blank = () => initialValues(rulesSchema)

test('quantity cannot exceed the selected item stock', () => {
  const values = { ...blank(), Feed_Item_ID: 'FEED-003', Quantity_Kg: '401' }
  assert.equal(validateForm(rulesSchema, values).Quantity_Kg, 'Only 400 available for FEED-003.')
  assert.equal(validateForm(rulesSchema, { ...values, Quantity_Kg: '400' }).Quantity_Kg, undefined)
})

test('editing gives back this record\'s own earlier usage of the same item', () => {
  const original = { ...blank(), Feed_Item_ID: 'FEED-002', Quantity_Kg: '100' }
  // 620 still in stock + 100 already used by this record = 700 allowed.
  assert.equal(validateForm(rulesSchema, { ...original, Quantity_Kg: '700' }, original).Quantity_Kg, undefined)
  assert.match(validateForm(rulesSchema, { ...original, Quantity_Kg: '721' }, original).Quantity_Kg ?? '', /Only 720/)
})

test('used cannot exceed opening + received', () => {
  const values = { ...blank(), Opening_Stock: '100', Received_Qty: '50', Used_Qty: '151' }
  assert.equal(validateForm(rulesSchema, values).Used_Qty, "Used QTY (151) can't exceed Opening_Stock + Received_Qty (150).")
  assert.equal(validateForm(rulesSchema, { ...values, Used_Qty: '150' }).Used_Qty, undefined)
})

test('percent and rating ranges', () => {
  const errors = validateForm(rulesSchema, { ...blank(), Progress_Percent: '150', Rating: '5.5' })
  assert.equal(errors.Progress_Percent, 'Must be between 0 and 100.')
  assert.equal(errors.Rating, 'Must be between 0 and 5.')
})

test('due date cannot be before start date', () => {
  const errors = validateForm(rulesSchema, { ...blank(), Start_Date: '2026-10-11', Due_Date: '2026-10-01' })
  assert.equal(errors.Due_Date, "Due Date can't be before Start Date.")
})

test('email, phone and time formats', () => {
  const errors = validateForm(rulesSchema, { ...blank(), Email: 'nope', Phone: 'call me', Reading_Time: '25:00' })
  assert.match(errors.Email, /valid email/)
  assert.match(errors.Phone, /valid phone/)
  assert.match(errors.Reading_Time, /valid time/)
  const ok = validateForm(rulesSchema, { ...blank(), Email: 'a@b.co', Phone: '+91 90000 00001', Reading_Time: '06:30' })
  assert.deepEqual([ok.Email, ok.Phone, ok.Reading_Time], [undefined, undefined, undefined])
})

test('constant defaults pre-fill new records', () => {
  const withDefault: EntitySchema = { ...rulesSchema, fields: [field({ name: 'Farm_ID', default: 'FARM-001' })] }
  assert.equal(initialValues(withDefault).Farm_ID, 'FARM-001')
})
