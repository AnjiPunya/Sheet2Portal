import { useState, type ReactNode } from 'react'
import { Dialog, PrimaryButton } from './Dialog'

/** Confirmation step for destructive or consequential actions. With
 * `withComment`, collects an optional comment (e.g. a rejection reason). */
export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  tone = 'indigo',
  withComment = false,
  commentLabel = 'Comment (optional)',
  isPending = false,
  error,
  onConfirm,
  onCancel,
}: {
  title: string
  message: ReactNode
  confirmLabel: string
  tone?: 'indigo' | 'red' | 'emerald'
  withComment?: boolean
  commentLabel?: string
  isPending?: boolean
  error?: string | null
  onConfirm: (comment: string) => void
  onCancel: () => void
}) {
  const [comment, setComment] = useState('')
  return (
    <Dialog
      title={title}
      onClose={onCancel}
      size="sm"
      zIndex="z-[70]"
      footer={
        <>
          <button onClick={onCancel} className="btn-secondary" disabled={isPending}>
            Cancel
          </button>
          <PrimaryButton tone={tone} onClick={() => onConfirm(comment.trim())} disabled={isPending}>
            {isPending ? 'Working…' : confirmLabel}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4 text-sm text-slate-600">
        <div>{message}</div>
        {withComment && (
          <label className="block">
            <span className="font-medium text-slate-700">{commentLabel}</span>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              maxLength={1000}
              rows={3}
              className="input mt-1 w-full resize-y"
            />
          </label>
        )}
        {error && (
          <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-700">
            {error}
          </p>
        )}
      </div>
    </Dialog>
  )
}
