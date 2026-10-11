import { useEffect, useRef, useState } from 'react'
import { useAuth } from './authContext'

export function UserMenu() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const initial = (user.display_name || user.email).slice(0, 1).toUpperCase()

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    window.addEventListener('mousedown', close)
    return () => window.removeEventListener('mousedown', close)
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-800 text-sm font-semibold text-white shadow-sm hover:bg-slate-700"
      >
        {initial}
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-40 mt-2 w-60 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg">
          <div className="px-3 py-2">
            <p className="truncate text-sm font-medium text-slate-800">{user.display_name}</p>
            <p className="truncate text-xs text-slate-500">{user.email}</p>
            <p className="mt-1 inline-block rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600 capitalize">
              {user.role}
            </p>
          </div>
          <button
            role="menuitem"
            onClick={logout}
            className="w-full rounded-lg px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}
