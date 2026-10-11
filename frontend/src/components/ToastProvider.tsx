import { useCallback, useState, type ReactNode } from 'react'
import { ToastContext, type ToastTone } from './toastContext'

interface Toast {
  id: number
  tone: ToastTone
  message: string
}

/** Success / error feedback after an action, auto-dismissed. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const show = useCallback((message: string, tone: ToastTone = 'success') => {
    const id = Date.now() + Math.random()
    setToasts((current) => [...current, { id, tone, message }])
    window.setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), tone === 'error' ? 6000 : 3500)
  }, [])

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 top-[calc(env(safe-area-inset-top,0px)+1rem)] z-[80] flex flex-col items-center gap-2 px-4" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.tone === 'error' ? 'alert' : 'status'}
            className={`pointer-events-auto flex max-w-md items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium text-white shadow-lg ${
              t.tone === 'error' ? 'bg-red-600' : 'bg-slate-900'
            }`}
          >
            <span aria-hidden>{t.tone === 'error' ? '⚠' : '✓'}</span>
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
