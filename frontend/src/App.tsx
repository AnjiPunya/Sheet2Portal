import { useCallback, useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchWorkbook, listWorkbooks, uploadWorkbook } from './api/workbooks'
import { fetchPortalConfig } from './api/portal'
import { fetchCurrentUser, logOut } from './api/auth'
import { ApiRequestError, AUTH_EXPIRED_EVENT } from './api/client'
import { UploadDropzone } from './components/UploadDropzone'
import { ErrorBanner } from './components/ErrorBanner'
import { Portal } from './components/Portal'
import { AuthPage } from './components/AuthPage'
import { AuthContext, useAuth, type AuthState } from './components/authContext'
import { UserMenu } from './components/UserMenu'
import type { CurrentUser } from './types/auth'
import type { WorkbookSummary } from './types/workbook'

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

/** Protected portal access: nothing below renders without a valid session. */
export default function App() {
  const queryClient = useQueryClient()
  const userQuery = useQuery({ queryKey: ['auth', 'me'], queryFn: fetchCurrentUser, staleTime: Infinity, retry: false })

  const setUser = useCallback(
    (user: CurrentUser | null) => {
      if (!user) queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== 'auth' })
      queryClient.setQueryData(['auth', 'me'], user)
    },
    [queryClient],
  )

  // Any 401 (expired or revoked session) drops back to the sign-in screen.
  useEffect(() => {
    const onExpired = () => setUser(null)
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired)
  }, [setUser])

  const user = userQuery.data
  const auth = useMemo<AuthState | null>(
    () =>
      user
        ? {
            user,
            can: (permission) => user.permissions.includes(permission),
            logout: () => {
              logOut().finally(() => {
                setWorkbookIdInUrl(null)
                setUser(null)
              })
            },
          }
        : null,
    [user, setUser],
  )

  if (userQuery.isLoading) {
    return <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">Loading…</div>
  }
  if (userQuery.isError) {
    return (
      <div className="mx-auto max-w-md px-4 py-16">
        <ErrorBanner code="CONNECTION_ERROR" message="Couldn't reach the server. Check that the backend is running, then reload." />
      </div>
    )
  }
  if (!auth) return <AuthPage onAuthenticated={setUser} />

  return (
    <AuthContext.Provider value={auth}>
      <Workspace />
    </AuthContext.Provider>
  )
}

function Workspace() {
  const { can } = useAuth()
  const [workbookId, setWorkbookId] = useState<string | null>(getWorkbookIdFromUrl)

  const uploadMutation = useMutation({
    mutationFn: uploadWorkbook,
    onSuccess: (workbook) => {
      setWorkbookId(workbook.id)
      setWorkbookIdInUrl(workbook.id)
    },
  })

  const workbooksQuery = useQuery({ queryKey: ['workbooks'], queryFn: listWorkbooks, enabled: workbookId === null })

  function openWorkbook(id: string) {
    setWorkbookId(id)
    setWorkbookIdInUrl(id)
  }

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
    workbooksQuery.refetch()
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
    <div className="min-h-screen bg-slate-50 py-10">
      <div className="mx-auto max-w-4xl px-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Sheet2Portal</h1>
            <p className="mt-1 text-slate-500">Upload a workbook and get a working business portal.</p>
          </div>
          <UserMenu />
        </div>

        <div className="mt-8">
          {!workbook && (
            <>
              {can('workbooks:upload') ? (
                <UploadDropzone onFileSelected={(file) => uploadMutation.mutate(file)} disabled={isLoading} />
              ) : (
                <p className="panel px-5 py-4 text-sm text-slate-600">Your role can view portals but not upload workbooks.</p>
              )}
              {isLoading && <p className="mt-3 text-sm text-slate-500">Processing…</p>}
              {loadError && (
                <div className="mt-4">
                  <ErrorBanner code={loadError.errorCode} message={loadError.message} />
                </div>
              )}
              <YourPortals workbooks={workbooksQuery.data} onOpen={openWorkbook} />
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

function YourPortals({ workbooks, onOpen }: { workbooks: WorkbookSummary[] | undefined; onOpen: (id: string) => void }) {
  const ready = (workbooks ?? []).filter((w) => w.status === 'ready')
  if (ready.length === 0) return null
  return (
    <section className="mt-10">
      <h2 className="section-label mb-3">Your portals</h2>
      <ul className="panel divide-y divide-slate-100">
        {ready.map((w) => (
          <li key={w.id}>
            <button
              onClick={() => onOpen(w.id)}
              className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-slate-50"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-slate-800">{w.display_title || w.original_filename}</span>
                <span className="text-xs text-slate-500">
                  {w.original_filename} · uploaded {new Date(w.created_at).toLocaleDateString()}
                </span>
              </span>
              <span className="text-sm text-indigo-600" aria-hidden>
                Open →
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
