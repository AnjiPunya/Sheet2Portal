import { createContext, useContext } from 'react'
import type { CurrentUser, Permission } from '../types/auth'

export interface AuthState {
  user: CurrentUser
  /** UI hint only -- the backend enforces every permission itself. */
  can: (permission: Permission) => boolean
  logout: () => void
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth must be used inside <AuthContext.Provider>')
  return auth
}
