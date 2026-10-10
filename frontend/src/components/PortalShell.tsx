import type { ReactNode } from 'react'
import type { PortalConfig } from '../types/portal'

export type PortalView = 'dashboard' | 'diagnostics' | { worksheet: string }

interface Props {
  config: PortalConfig
  view: PortalView
  onNavigate: (view: PortalView) => void
  onReset: () => void
  children: ReactNode
}

function viewKey(view: PortalView): string {
  return typeof view === 'string' ? view : `entity:${view.worksheet}`
}

export function PortalShell({ config, view, onNavigate, onReset, children }: Props) {
  const activeKey = viewKey(view)

  return (
    <div className="min-h-screen bg-slate-100">
      <div className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600 font-semibold text-white">
              {config.title.slice(0, 1).toUpperCase()}
            </div>
            <div>
              <h1 className="text-lg font-semibold text-slate-900">{config.title}</h1>
              <p className="text-xs text-slate-400">Generated portal · {config.entities.length} entities</p>
            </div>
          </div>
          <button
            onClick={onReset}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
          >
            Upload another file
          </button>
        </div>
        <nav className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-4">
          <button
            onClick={() => onNavigate('dashboard')}
            className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors
              ${activeKey === 'dashboard' ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
          >
            Dashboard
          </button>
          {config.entities.map((entity) => (
            <button
              key={entity.worksheet}
              onClick={() => onNavigate({ worksheet: entity.worksheet })}
              className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors
                ${activeKey === `entity:${entity.worksheet}` ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
            >
              {entity.label}
            </button>
          ))}
          <button
            onClick={() => onNavigate('diagnostics')}
            className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors
              ${activeKey === 'diagnostics' ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
          >
            Diagnostics
          </button>
        </nav>
      </div>
      <div className="mx-auto max-w-6xl px-4 py-6">{children}</div>
    </div>
  )
}
