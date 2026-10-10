import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { fetchWorkbook, uploadWorkbook } from './api/workbooks'
import { fetchPortalConfig } from './api/portal'
import { ApiRequestError } from './api/client'
import { UploadDropzone } from './components/UploadDropzone'
import { ErrorBanner } from './components/ErrorBanner'
import { Portal } from './components/Portal'

function getWorkbookIdFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get('workbook')
}

function setWorkbookIdInUrl(id: string | null) {
  const url = new URL(window.location.href)
  if (id) {
    url.searchParams.set('workbook', id)
  } else {
    url.searchParams.delete('workbook')
  }
  window.history.pushState({}, '', url)
}

export default function App() {
  const [workbookId, setWorkbookId] = useState<string | null>(getWorkbookIdFromUrl)

  const uploadMutation = useMutation({
    mutationFn: uploadWorkbook,
    onSuccess: (workbook) => {
      setWorkbookId(workbook.id)
      setWorkbookIdInUrl(workbook.id)
    },
  })

  const workbookQuery = useQuery({
    queryKey: ['workbook', workbookId],
    queryFn: () => fetchWorkbook(workbookId!),
    enabled: workbookId !== null && uploadMutation.data?.id !== workbookId,
  })

  const workbook = uploadMutation.data ?? workbookQuery.data

  const portalQuery = useQuery({
    queryKey: ['portal', workbook?.id],
    queryFn: () => fetchPortalConfig(workbook!.id),
    enabled: !!workbook && workbook.status === 'ready',
  })

  function reset() {
    setWorkbookId(null)
    setWorkbookIdInUrl(null)
    uploadMutation.reset()
  }

  const isLoading = uploadMutation.isPending || workbookQuery.isLoading || (workbook?.status === 'ready' && portalQuery.isLoading)
  const loadError =
    uploadMutation.error instanceof ApiRequestError
      ? uploadMutation.error
      : workbookQuery.error instanceof ApiRequestError
        ? workbookQuery.error
        : portalQuery.error instanceof ApiRequestError
          ? portalQuery.error
          : null

  if (workbook && workbook.status === 'ready' && portalQuery.data) {
    return (
      <Portal workbookId={workbook.id} workbook={workbook} config={portalQuery.data} onReset={reset} />
    )
  }

  return (
    <div className="min-h-screen bg-slate-100 py-10">
      <div className="mx-auto max-w-4xl px-4">
        <h1 className="text-2xl font-semibold text-slate-900">Sheet2Portal</h1>
        <p className="mt-1 text-slate-500">Upload a workbook and get a working business portal.</p>

        <div className="mt-8">
          {!workbook && (
            <>
              <UploadDropzone onFileSelected={(file) => uploadMutation.mutate(file)} disabled={isLoading} />
              {isLoading && <p className="mt-3 text-sm text-slate-500">Processing…</p>}
              {loadError && (
                <div className="mt-4">
                  <ErrorBanner code={loadError.errorCode} message={loadError.message} />
                </div>
              )}
            </>
          )}

          {workbook && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="font-medium text-slate-800">{workbook.original_filename}</h2>
                <button onClick={reset} className="text-sm text-indigo-600 hover:underline">
                  Upload another file
                </button>
              </div>

              {workbook.status === 'error' && (
                <ErrorBanner
                  code={workbook.error_code ?? 'PARSE_ERROR'}
                  message={workbook.error_message ?? 'Could not process this file.'}
                />
              )}

              {workbook.status === 'ready' && isLoading && (
                <p className="text-sm text-slate-500">Generating portal…</p>
              )}

              {workbook.status === 'ready' && loadError && (
                <ErrorBanner code={loadError.errorCode} message={loadError.message} />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
