import { apiFetch, jsonRequest, throwApiError } from './client'
import type { CurrentUser } from '../types/auth'

/** The signed-in user, or null when there's no valid session. */
export async function fetchCurrentUser(): Promise<CurrentUser | null> {
  const res = await apiFetch('/api/auth/me')
  if (res.status === 401) return null
  if (!res.ok) return throwApiError(res)
  return res.json()
}

export function signUp(email: string, password: string, displayName: string): Promise<CurrentUser> {
  return jsonRequest('/api/auth/signup', 'POST', { email, password, display_name: displayName })
}

export function logIn(email: string, password: string): Promise<CurrentUser> {
  return jsonRequest('/api/auth/login', 'POST', { email, password })
}

export function logOut(): Promise<void> {
  return jsonRequest('/api/auth/logout', 'POST')
}
