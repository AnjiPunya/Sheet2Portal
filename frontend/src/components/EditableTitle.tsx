import { useEffect, useRef, useState } from 'react'

export function EditableTitle({
  value,
  onSave,
  isSaving = false,
  className = '',
  inputClassName = '',
}: {
  value: string
  onSave: (newValue: string) => void
  isSaving?: boolean
  className?: string
  inputClassName?: string
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!editing) setDraft(value)
  }, [value, editing])

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [editing])

  function commit() {
    setEditing(false)
    const trimmed = draft.trim()
    if (trimmed !== value) onSave(trimmed)
  }

  function cancel() {
    setDraft(value)
    setEditing(false)
  }

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit()
          if (e.key === 'Escape') cancel()
        }}
        placeholder="Portal title"
        disabled={isSaving}
        className={`rounded border border-indigo-300 bg-white px-1.5 py-0.5 outline-none focus:border-indigo-500 ${inputClassName}`}
      />
    )
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      className={`group flex items-center gap-1.5 text-left ${className}`}
      title="Click to rename this portal"
    >
      <span>{value}</span>
      <svg
        className="h-3.5 w-3.5 flex-shrink-0 text-slate-300 opacity-0 transition-opacity group-hover:opacity-100"
        viewBox="0 0 20 20"
        fill="currentColor"
      >
        <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
      </svg>
    </button>
  )
}
