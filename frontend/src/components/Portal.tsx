import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { WorkbookOut } from '../types/workbook'
import type { PortalConfig } from '../types/portal'
import { updateWorkbookTitle } from '../api/workbooks'
import { formatLabel } from '../lib/labels'
import { clearRelatedFilter, entityPageKey, entityView, relatedEntityView, type PortalView } from '../lib/portalView'
import { PortalNavContext, type PortalNav } from './portalContext'
import { PortalShell } from './PortalShell'
import { Dashboard } from './Dashboard'
import { EntityView } from './EntityView'
import { WorksheetTabs } from './WorksheetTabs'
import { SampleTable } from './SampleTable'
import { ErrorBanner } from './ErrorBanner'
import { ChatWidget } from './ChatWidget'

export function Portal({
  workbookId,
  workbook,
  config,
  onReset,
}: {
  workbookId: string
  workbook: WorkbookOut
  config: PortalConfig
  onReset: () => void
}) {
  const [view, setView] = useState<PortalView>('dashboard')
  const [diagnosticsSheetIndex, setDiagnosticsSheetIndex] = useState(0)
  const queryClient = useQueryClient()

  const activeEntity = typeof view === 'object' ? config.entities.find((e) => e.worksheet === view.worksheet) : null

  const nav = useMemo<PortalNav>(() => {
    const byWorksheet = new Map(config.entities.map((e) => [e.worksheet, e]))
    return {
      labelFor: (worksheet) => formatLabel(byWorksheet.get(worksheet)?.label ?? worksheet),
      titleColumnFor: (worksheet) => byWorksheet.get(worksheet)?.title_column ?? null,
      openEntity: (worksheet) => setView(entityView(worksheet)),
      openRelated: (worksheet, parent) => setView(relatedEntityView(worksheet, parent)),
    }
  }, [config.entities])

  useEffect(() => {
    document.title = config.title ? `${config.title} · Sheet2Portal` : 'Sheet2Portal'
    return () => {
      document.title = 'Sheet2Portal'
    }
  }, [config.title])

  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [view])

  const titleMutation = useMutation({
    mutationFn: (title: string) => updateWorkbookTitle(workbookId, title),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portal', workbookId] })
    },
  })

  return (
    <PortalNavContext.Provider value={nav}>
      <PortalShell
        config={config}
        view={view}
        onNavigate={setView}
        onReset={onReset}
        onUpdateTitle={(title) => titleMutation.mutate(title)}
        isSavingTitle={titleMutation.isPending}
      >
        {view === 'dashboard' && <Dashboard workbookId={workbookId} config={config} />}

        {activeEntity && typeof view === 'object' && (
          <div className="space-y-5">
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-slate-900">{nav.labelFor(activeEntity.worksheet)}</h2>
              <p className="mt-0.5 text-sm text-slate-500">
                {activeEntity.row_count} {activeEntity.row_count === 1 ? 'record' : 'records'} in this worksheet
              </p>
            </div>
            <EntityView
              key={entityPageKey(view)}
              workbookId={workbookId}
              entity={activeEntity}
              related={view.related}
              onClearRelated={() => setView(clearRelatedFilter(view))}
            />
          </div>
        )}

        {view === 'diagnostics' && (
          <div className="space-y-4">
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-slate-900">Diagnostics</h2>
              <p className="mt-0.5 text-sm text-slate-500">
                Raw worksheet preview, exactly as parsed from the uploaded file (original column names) — useful for
                verifying the upload independent of the generated portal.
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Original file: <span className="font-mono text-slate-500">{workbook.original_filename}</span>
              </p>
            </div>
            <WorksheetTabs sheets={workbook.worksheets} activeIndex={diagnosticsSheetIndex} onSelect={setDiagnosticsSheetIndex} />
            {workbook.worksheets[diagnosticsSheetIndex] && (
              <>
                {workbook.worksheets[diagnosticsSheetIndex].warning && (
                  <ErrorBanner
                    code="Heads up"
                    message={workbook.worksheets[diagnosticsSheetIndex].warning!}
                    variant="warning"
                  />
                )}
                <SampleTable sheet={workbook.worksheets[diagnosticsSheetIndex]} />
              </>
            )}
          </div>
        )}

        <ChatWidget workbookId={workbookId} portalTitle={config.title} />
      </PortalShell>
    </PortalNavContext.Provider>
  )
}
