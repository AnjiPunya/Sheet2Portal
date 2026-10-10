import { useState } from 'react'
import type { WorkbookOut } from '../types/workbook'
import type { PortalConfig } from '../types/portal'
import { PortalShell, type PortalView } from './PortalShell'
import { Dashboard } from './Dashboard'
import { EntityView } from './EntityView'
import { WorksheetTabs } from './WorksheetTabs'
import { SampleTable } from './SampleTable'
import { ErrorBanner } from './ErrorBanner'

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

  const activeEntity = typeof view === 'object' ? config.entities.find((e) => e.worksheet === view.worksheet) : null
  const titleColumnByWorksheet = Object.fromEntries(config.entities.map((e) => [e.worksheet, e.title_column]))

  return (
    <PortalShell config={config} view={view} onNavigate={setView} onReset={onReset}>
      {view === 'dashboard' && (
        <Dashboard
          workbookId={workbookId}
          config={config}
          titleColumnByWorksheet={titleColumnByWorksheet}
          onNavigateEntity={(worksheet) => setView({ worksheet })}
        />
      )}

      {activeEntity && (
        <div>
          <h2 className="mb-4 text-lg font-semibold text-slate-800">{activeEntity.label}</h2>
          <EntityView
            key={activeEntity.worksheet}
            workbookId={workbookId}
            entity={activeEntity}
            titleColumnByWorksheet={titleColumnByWorksheet}
            onNavigateEntity={(worksheet) => setView({ worksheet })}
          />
        </div>
      )}

      {view === 'diagnostics' && (
        <div className="space-y-4">
          <p className="text-sm text-slate-500">
            Raw worksheet preview, as parsed from the uploaded file — useful for verifying the upload independent
            of the generated portal above.
          </p>
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
    </PortalShell>
  )
}
