export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiRequestError extends Error {
  errorCode: string

  constructor(errorCode: string, message: string) {
    super(message)
    this.errorCode = errorCode
  }
}

export async function throwApiError(res: Response): Promise<never> {
  const body = await res.json().catch(() => null)
  const detail = body?.detail
  throw new ApiRequestError(detail?.error_code ?? 'UNKNOWN_ERROR', detail?.message ?? res.statusText)
}
