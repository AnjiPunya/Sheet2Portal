export type AuthMode = 'login' | 'signup'

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

/** Client-side checks mirror the backend's (app/schemas/auth.py) so users get
 * instant feedback; the backend validates again regardless. */
export function validateAuthForm(mode: AuthMode, email: string, password: string): string | null {
  if (!EMAIL_RE.test(email.trim())) return 'Enter a valid email address.'
  if (mode === 'login') return password ? null : 'Enter your password.'
  if (password.length < 8 || !/[A-Za-z]/.test(password) || !/\d/.test(password)) {
    return 'Password must be at least 8 characters and include a letter and a number.'
  }
  return null
}
