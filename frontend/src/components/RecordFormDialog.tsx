import { useMemo, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createRecord, fetchEntitySchema, updateRecord } from '../api/records'
import { ApiRequestError } from '../api/client'
import { applyChange, buildPayload, initialValues, previewComputed, validateForm, type FormValues } from '../lib/recordForm'
import { invalidateWorkbookData } from '../lib/invalidate'
import { formatLabel } from '../lib/labels'
import type { EntitySchema, FieldSpec, RecordWriteResult } from '../types/records'
import { Dialog, PrimaryButton } from './Dialog'
import { useToast } from './toastContext'

const NUMBER_FORMAT = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })

/** Generic create / edit dialog for any worksheet, driven by the backend schema. */
export function RecordFormDialog({
  workbookId,
  worksheet,
  record,
  onClose,
  onSaved,
}: {
  workbookId: string
  worksheet: string
  /** Present when editing. */
  record?: { id: string; data: Record<string, unknown> }
  onClose: () => void
  onSaved?: (result: RecordWriteResult) => void
}) {
  const schemaQuery = useQuery({
    queryKey: ['entity-schema', workbookId, worksheet],
    queryFn: () => fetchEntitySchema(workbookId, worksheet),
  })

  return (
    <Dialog
      title={record ? 'Edit record' : `New ${schemaQuery.data?.singular_label.toLowerCase() ?? 'record'}`}
      subtitle={schemaQuery.data?.label}
      onClose={onClose}
      size="lg"
    >
      {schemaQuery.isLoading && <p className="text-sm text-slate-500">Loading form…</p>}
      {schemaQuery.error && (
        <p className="text-sm text-red-700">
          {schemaQuery.error instanceof ApiRequestError ? schemaQuery.error.message : 'Could not load the form.'}
        </p>
      )}
      {schemaQuery.data && (
        <RecordForm
          workbookId={workbookId}
          worksheet={worksheet}
          schema={schemaQuery.data}
          record={record}
          onClose={onClose}
          onSaved={onSaved}
        />
      )}
    </Dialog>
  )
}

function RecordForm({
  workbookId,
  worksheet,
  schema,
  record,
  onClose,
  onSaved,
}: {
  workbookId: string
  worksheet: string
  schema: EntitySchema
  record?: { id: string; data: Record<string, unknown> }
  onClose: () => void
  onSaved?: (result: RecordWriteResult) => void
}) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const original = useMemo(() => initialValues(schema, record?.data), [schema, record])
  const [values, setValues] = useState<FormValues>(original)
  const [touched] = useState(() => new Set<string>(record ? schema.fields.map((f) => f.name) : []))
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({})

  const mutation = useMutation({
    mutationFn: () => {
      const payload = buildPayload(schema, values, record ? original : undefined)
      return record ? updateRecord(workbookId, worksheet, record.id, payload) : createRecord(workbookId, worksheet, payload)
    },
    onSuccess: (result) => {
      invalidateWorkbookData(queryClient, workbookId)
      toast(record ? 'Changes saved' : `${schema.singular_label} created`)
      onSaved?.(result)
      onClose()
    },
  })

  const computed = previewComputed(schema, values)
  // Field messages from the server (422) show next to their inputs.
  const serverFields = mutation.error instanceof ApiRequestError ? mutation.error.fields : {}
  const errors = { ...serverFields, ...clientErrors }
  const hasFieldErrors = Object.keys(serverFields).length > 0
  const generalError =
    mutation.error && !hasFieldErrors
      ? mutation.error instanceof ApiRequestError
        ? mutation.error.message
        : 'Something went wrong. Please try again.'
      : null

  function change(name: string, value: string | boolean) {
    touched.add(name)
    const next = applyChange(schema, values, name, value, touched)
    setValues(next)
    // Clear errors on every field whose value changed -- including ones
    // filled in automatically (e.g. Unit Cost after choosing a material).
    setClientErrors((current) => Object.fromEntries(Object.entries(current).filter(([field]) => next[field] === values[field])))
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    const problems = validateForm(schema, values, record ? original : undefined)
    setClientErrors(problems)
    if (Object.keys(problems).length === 0) mutation.mutate()
  }

  const visible = schema.fields.filter((f) => !(f.workflow && !record))

  return (
    <form onSubmit={submit} noValidate className="space-y-5">
      <div className="grid grid-cols-1 gap-x-5 gap-y-4 sm:grid-cols-2">
        {visible.map((field) => (
          <FieldInput
            key={field.name}
            field={field}
            value={values[field.name]}
            computedValue={field.computed ? computed[field.name] : undefined}
            autoPlaceholder={field.auto_by ? field.auto_by.next[String(values[field.auto_by.column] ?? '')] ?? null : undefined}
            error={errors[field.name]}
            onChange={(v) => change(field.name, v)}
          />
        ))}
      </div>

      {schema.workflow && !record && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
          New {schema.singular_label.toLowerCase()}s start as <strong>{schema.workflow.pending}</strong> and wait for approval.
        </p>
      )}

      {(generalError || errors._) && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {generalError ?? errors._}
        </p>
      )}

      <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
        <button type="button" onClick={onClose} className="btn-secondary" disabled={mutation.isPending}>
          Cancel
        </button>
        <PrimaryButton type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? 'Saving…' : record ? 'Save changes' : `Create ${schema.singular_label.toLowerCase()}`}
        </PrimaryButton>
      </div>
    </form>
  )
}

function FieldInput({
  field,
  value,
  computedValue,
  autoPlaceholder,
  error,
  onChange,
}: {
  field: FieldSpec
  value: string | boolean | undefined
  computedValue: number | null | undefined
  autoPlaceholder?: string | null
  error?: string
  onChange: (value: string | boolean) => void
}) {
  const id = `field-${field.name.replace(/\W+/g, '-')}`
  const hintText = field.computed ?? field.hint ?? (field.lookup ? `Filled from the selected ${field.lookup.entity.toLowerCase()} record; you can change it.` : null)
  const describedBy = error ? `${id}-error` : hintText ? `${id}-hint` : undefined
  const invalid = error ? 'border-red-300 focus:border-red-400 focus:ring-red-100' : ''

  let control
  if (field.computed) {
    control = (
      <div id={id} className="flex h-[38px] items-center rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 text-sm font-semibold text-slate-800 tabular-nums">
        {computedValue === null || computedValue === undefined ? '—' : NUMBER_FORMAT.format(computedValue)}
      </div>
    )
  } else if (field.readonly) {
    control = (
      <div id={id} className="flex h-[38px] items-center rounded-lg bg-slate-50 px-3 text-sm text-slate-600">
        {String(value || field.default || '—')}
      </div>
    )
  } else if (field.input === 'checkbox') {
    control = (
      <input id={id} type="checkbox" checked={value === true} onChange={(e) => onChange(e.target.checked)} className="h-4 w-4 rounded border-slate-300" />
    )
  } else if (field.input === 'select') {
    control = (
      <select
        id={id}
        value={typeof value === 'string' ? value : ''}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        className={`input w-full ${invalid}`}
      >
        <option value="">{field.required ? 'Select…' : '—'}</option>
        {(field.options ?? []).map((option) => (
          <option key={option} value={option}>
            {field.option_labels?.[option] ?? option}
          </option>
        ))}
      </select>
    )
  } else {
    const listId = field.suggestions ? `${id}-suggestions` : undefined
    control = (
      <>
        <input
          id={id}
          type={field.input}
          // Numbers: the browser only accepts digits; step/min/max mirror the backend rules.
          step={field.input === 'number' ? (field.type === 'int' ? 1 : 'any') : undefined}
          min={field.input === 'number' && field.min !== null && field.min !== undefined ? field.min : undefined}
          max={field.input === 'number' && field.max !== null && field.max !== undefined ? field.max : undefined}
          inputMode={field.input === 'number' ? (field.type === 'int' ? 'numeric' : 'decimal') : field.input === 'tel' ? 'tel' : undefined}
          autoComplete={field.input === 'email' ? 'email' : field.input === 'tel' ? 'tel' : undefined}
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={
            autoPlaceholder !== undefined
              ? autoPlaceholder
                ? `Auto: ${autoPlaceholder}`
                : `Choose ${field.auto_by ? formatLabel(field.auto_by.column) : 'a type'} to generate`
              : field.placeholder
                ? `Auto: ${field.placeholder}`
                : undefined
          }
          list={listId}
          aria-invalid={!!error}
          aria-describedby={describedBy}
          className={`input w-full ${invalid}`}
        />
        {listId && (
          <datalist id={listId}>
            {field.suggestions!.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
        )}
      </>
    )
  }

  return (
    <div className={field.input === 'checkbox' ? 'flex items-center gap-2 sm:col-span-2' : ''}>
      <label htmlFor={id} className="text-sm font-medium text-slate-700">
        {field.label}
        {field.required && <span className="text-red-500"> *</span>}
        {field.computed && <span className="ml-1.5 rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-700">CALCULATED</span>}
      </label>
      <div className={field.input === 'checkbox' ? '' : 'mt-1'}>{control}</div>
      {error ? (
        <p id={`${id}-error`} className="mt-1 text-xs text-red-600">
          {error}
        </p>
      ) : hintText ? (
        <p id={`${id}-hint`} className="mt-1 text-xs text-slate-500">
          {hintText}
        </p>
      ) : null}
    </div>
  )
}
