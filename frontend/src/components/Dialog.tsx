import { useEffect, type ReactNode } from 'react'

/** Shared modal shell: overlay, Escape to close, bottom sheet on phones. */
export function Dialog({
  title,
  subtitle,
  onClose,
  children,
  footer,
  size = 'md',
  zIndex = 'z-[60]',
}: {
  title: ReactNode
  subtitle?: ReactNode
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg'
  zIndex?: string
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const width = { sm: 'max-w-md', md: 'max-w-xl', lg: 'max-w-2xl' }[size]

  return (
    <div
      className={`fixed inset-0 ${zIndex} flex items-end justify-center bg-slate-900/50 backdrop-blur-[2px] sm:items-center sm:p-6`}
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className={`flex max-h-[92vh] w-full ${width} flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl sm:rounded-2xl`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 pt-4 pb-3 sm:px-6">
          <div className="min-w-0">
            <h3 className="text-lg font-semibold tracking-tight text-slate-900">{title}</h3>
            {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="-mt-1 -mr-1 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden>
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4 sm:px-6 sm:py-5">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 bg-slate-50/60 px-5 py-3 sm:px-6">{footer}</div>}
      </div>
    </div>
  )
}

export function PrimaryButton({
  children,
  tone = 'indigo',
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: 'indigo' | 'red' | 'emerald' }) {
  const tones = {
    indigo: 'bg-indigo-600 hover:bg-indigo-700',
    red: 'bg-red-600 hover:bg-red-700',
    emerald: 'bg-emerald-600 hover:bg-emerald-700',
  }
  return (
    <button
      {...props}
      className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold text-white shadow-sm transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${tones[tone]} ${props.className ?? ''}`}
    >
      {children}
    </button>
  )
}
