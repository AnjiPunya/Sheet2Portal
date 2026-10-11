import type { ReactNode } from 'react'
import type { PortalConfig } from '../types/portal'
import { entityView, navKey, type PortalView } from '../lib/portalView'
import { usePortalNav } from './portalContext'
import { EditableTitle } from './EditableTitle'

interface Props {
  config: PortalConfig
  view: PortalView
  onNavigate: (view: PortalView) => void
  onReset: () => void
  onUpdateTitle: (title: string) => void
  isSavingTitle?: boolean
  children: ReactNode
}

function NavTab({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className={`relative whitespace-nowrap px-3 py-2.5 text-sm font-medium transition-colors
        ${active ? 'text-indigo-700' : 'text-slate-500 hover:text-slate-800'}`}
    >
      {children}
      <span
        className={`absolute inset-x-2 -bottom-px h-0.5 rounded-full transition-colors ${active ? 'bg-indigo-600' : 'bg-transparent'}`}
      />
    </button>
  )
}

export function PortalShell({ config, view, onNavigate, onReset, onUpdateTitle, isSavingTitle, children }: Props) {
  const activeKey = navKey(view)
  const nav = usePortalNav()

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/80">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 pt-4 pb-2 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-700 text-base font-semibold text-white shadow-sm">
              {config.title.slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0">
              <EditableTitle
                value={config.title}
                onSave={onUpdateTitle}
                isSaving={isSavingTitle}
                className="truncate text-lg font-semibold tracking-tight text-slate-900"
              />
              <p className="text-xs text-slate-500">
                Generated portal · {config.entities.length} {config.entities.length === 1 ? 'entity' : 'entities'}
              </p>
            </div>
          </div>
          <button onClick={onReset} className="btn-secondary">
            <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden>
              <path d="M9.25 13.25a.75.75 0 001.5 0V4.636l2.955 3.129a.75.75 0 001.09-1.03l-4.25-4.5a.75.75 0 00-1.09 0l-4.25 4.5a.75.75 0 101.09 1.03L9.25 4.636v8.614z" />
              <path d="M3.5 12.75a.75.75 0 00-1.5 0v2.5A2.75 2.75 0 004.75 18h10.5A2.75 2.75 0 0018 15.25v-2.5a.75.75 0 00-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5z" />
            </svg>
            <span className="hidden sm:inline">Upload another file</span>
            <span className="sm:hidden">Upload</span>
          </button>
        </div>
        <nav className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-2 sm:px-4" aria-label="Portal sections">
          <NavTab active={activeKey === 'dashboard'} onClick={() => onNavigate('dashboard')}>
            Dashboard
          </NavTab>
          {config.entities.map((entity) => (
            <NavTab
              key={entity.worksheet}
              active={activeKey === `entity:${entity.worksheet}`}
              onClick={() => onNavigate(entityView(entity.worksheet))}
            >
              {nav.labelFor(entity.worksheet)}
            </NavTab>
          ))}
          <NavTab active={activeKey === 'diagnostics'} onClick={() => onNavigate('diagnostics')}>
            Diagnostics
          </NavTab>
        </nav>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">{children}</main>
    </div>
  )
}
