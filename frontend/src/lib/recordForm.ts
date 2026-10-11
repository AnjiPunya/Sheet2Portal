// Pure form logic for the generic record create/edit dialog (no React), so it
// can be unit-tested. The backend re-validates and recalculates everything;
// this only gives instant feedback and a live preview of calculated fields.
import type { EntitySchema, FieldSpec } from '../types/records.ts'

/** Form values are kept as strings (what inputs hold), booleans for checkboxes. */
export type FormValues = Record<string, string | boolean>

function toInput(value: unknown, field: FieldSpec): string | boolean {
  if (field.input === 'checkbox') return value === true
  if (value === null || value === undefined) return ''
  return String(value)
}

export function initialValues(schema: EntitySchema, record?: Record<string, unknown>): FormValues {
  const values: FormValues = {}
  for (const field of schema.fields) {
    const existing = record?.[field.name]
    values[field.name] = toInput(existing ?? (record ? null : field.default ?? null), field)
  }
  return values
}

function parseNumber(value: string | boolean | undefined): number | null {
  if (typeof value !== 'string' || value.trim() === '') return null
  const n = Number(value.replace(/,/g, ''))
  return Number.isFinite(n) ? n : null
}

/** When the field a lookup depends on changes (e.g. the selected material),
 * prefill the looked-up value (its unit cost) unless the user typed their own. */
export function applyChange(schema: EntitySchema, values: FormValues, name: string, value: string | boolean, touched: Set<string>): FormValues {
  const next = { ...values, [name]: value }
  for (const field of schema.fields) {
    if (field.lookup?.from === name && !touched.has(field.name)) {
      const looked = typeof value === 'string' ? field.lookup.defaults[value] : undefined
      next[field.name] = looked === undefined || looked === null ? '' : String(looked)
    }
  }
  return next
}

/** Live preview of calculated fields, using the same formulas the backend applies. */
export function previewComputed(schema: EntitySchema, values: FormValues): Record<string, number | null> {
  const out: Record<string, number | null> = {}
  for (const formula of schema.formulas) {
    const [a, b] = formula.factors.map((f) => parseNumber(values[f.column]))
    out[formula.target] = a === null || b === null ? null : Math.round(a * b * 100) / 100
  }
  return out
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const PHONE_RE = /^\+?[\d\s()-]{7,20}$/
const TIME_RE = /^([01]?\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/

const fmt = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 2 })

/** Field -> message for problems the browser can catch before submitting.
 * Mirrors the backend rules (app/services/records/validation.py), which
 * re-check everything regardless. */
export function validateForm(schema: EntitySchema, values: FormValues, original?: FormValues): Record<string, string> {
  const errors: Record<string, string> = {}
  const changed = (name: string) => original === undefined || values[name] !== original[name]
  const labelOf = (name: string) => schema.fields.find((f) => f.name === name)?.label ?? name

  for (const field of schema.fields) {
    if (field.readonly || field.computed) continue
    const value = values[field.name]
    const blank = value === '' || value === undefined
    // When editing, a field that was already blank in the workbook is only
    // required if the user changes it (matches the backend rule).
    const unchanged = !changed(field.name)
    const autoFillable = field.auto === 'next_id'
    if (field.required && blank && field.input !== 'checkbox' && !autoFillable) {
      if (!unchanged) errors[field.name] = `${field.label} is required.`
      continue
    }
    if (unchanged || blank || typeof value !== 'string') continue
    if (field.input === 'number') {
      const n = parseNumber(value)
      if (n === null) errors[field.name] = 'Enter a number.'
      else if (field.type === 'int' && !Number.isInteger(n)) errors[field.name] = 'Enter a whole number.'
      else if (field.min !== null && field.min !== undefined && n < field.min)
        errors[field.name] = field.min === 0 ? 'Must be zero or more.' : `Must be at least ${fmt(field.min)}.`
      else if (field.max !== null && field.max !== undefined && n > field.max)
        errors[field.name] = `Must be between ${fmt(field.min ?? 0)} and ${fmt(field.max)}.`
    } else if (field.input === 'date' && !DATE_RE.test(value)) {
      errors[field.name] = 'Enter a valid date (YYYY-MM-DD).'
    } else if (field.input === 'select' && field.options && !field.options.includes(value)) {
      errors[field.name] = 'Choose one of the options.'
    } else if (field.format === 'email' && !EMAIL_RE.test(value.trim())) {
      errors[field.name] = 'Enter a valid email address.'
    } else if (field.format === 'tel' && !PHONE_RE.test(value.trim())) {
      errors[field.name] = 'Enter a valid phone number (digits, spaces, + - ( ) only).'
    } else if (field.format === 'time' && !TIME_RE.test(value.trim())) {
      errors[field.name] = 'Enter a valid time (HH:MM).'
    }
  }

  // Cross-field business rules (checked when any field involved changed).
  for (const field of schema.fields) {
    if (errors[field.name] || field.readonly) continue
    const value = values[field.name]
    if (field.after && typeof value === 'string' && DATE_RE.test(value)) {
      const start = values[field.after]
      if ((changed(field.name) || changed(field.after)) && typeof start === 'string' && DATE_RE.test(start) && value < start) {
        errors[field.name] = `${field.label} can't be before ${labelOf(field.after)}.`
      }
    }
    const n = typeof value === 'string' ? parseNumber(value) : null
    if (n === null) continue
    if (field.max_sum && (changed(field.name) || field.max_sum.some(changed))) {
      const supply = field.max_sum.reduce((sum, name) => sum + (parseNumber(values[name] as string) ?? 0), 0)
      if (n > supply) errors[field.name] = `${field.label} (${fmt(n)}) can't exceed ${field.max_sum.map(labelOf).join(' + ')} (${fmt(supply)}).`
    }
    if (field.max_from && (changed(field.name) || changed(field.max_from.from))) {
      const item = values[field.max_from.from]
      let available = typeof item === 'string' ? field.max_from.available[item] : undefined
      if (available !== undefined && available !== null) {
        // Editing: this record's own earlier usage of the same item is given back.
        if (original && original[field.max_from.from] === item) available += parseNumber(original[field.name] as string) ?? 0
        if (n > available) errors[field.name] = `Only ${fmt(Math.max(available, 0))} available for ${item}.`
      }
    }
  }
  return errors
}

/** What to send: on create every editable field; on edit only what changed. */
export function buildPayload(
  schema: EntitySchema,
  values: FormValues,
  original?: FormValues,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  for (const field of schema.fields) {
    if (field.readonly || field.computed) continue
    const value = values[field.name]
    if (original && value === original[field.name]) continue
    if (field.input === 'checkbox') payload[field.name] = value === true
    else if (value === '' || value === undefined) {
      if (original) payload[field.name] = null
    } else if (field.input === 'number') payload[field.name] = parseNumber(value as string)
    else payload[field.name] = (value as string).trim()
  }
  return payload
}
