export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiRequestError extends Error {
  errorCode: string
  status: number
  /** Per-field messages from a validation failure (field name -> message). */
  fields: Record<string, string>

  constructor(errorCode: string, message: string, status = 0, fields: Record<string, string> = {}) {
    super(message)
    this.errorCode = errorCode
    this.status = status
    this.fields = fields
  }
}

/** Fired on any 401 so the app can drop back to the sign-in screen. */
export const AUTH_EXPIRED_EVENT = 'sheet2portal:auth-expired'

/** fetch() against the backend with the session cookie attached. The
 * session lives in an httpOnly cookie, so no token is ever handled (or
 * stored) by frontend code. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, credentials: 'include' })
  if (res.status === 401 && !path.startsWith('/api/auth/')) {
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
  }
  return res
}

export async function throwApiError(res: Response): Promise<never> {
  const body = await res.json().catch(() => null)
  const detail = body?.detail
  // FastAPI request-validation errors (422) arrive as a list; surface the first message.
  if (Array.isArray(detail)) {
    const first = detail[0]
    const message = typeof first?.msg === 'string' ? first.msg.replace(/^Value error, /, '') : res.statusText
    throw new ApiRequestError('VALIDATION_ERROR', message, res.status)
  }
  throw new ApiRequestError(detail?.error_code ?? 'UNKNOWN_ERROR', detail?.message ?? res.statusText, res.status, detail?.fields ?? {})
}

export async function jsonRequest<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await apiFetch(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) return throwApiError(res)
  if (res.status === 204) return undefined as T
  return res.json()
}
