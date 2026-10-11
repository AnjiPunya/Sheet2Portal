import { useState, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { logIn, signUp } from '../api/auth'
import { ApiRequestError } from '../api/client'
import type { CurrentUser } from '../types/auth'
import { validateAuthForm, type AuthMode as Mode } from '../lib/authValidation'

export function AuthPage({ onAuthenticated }: { onAuthenticated: (user: CurrentUser) => void }) {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => (mode === 'login' ? logIn(email.trim(), password) : signUp(email.trim(), password, displayName.trim())),
    onSuccess: onAuthenticated,
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    const problem = validateAuthForm(mode, email, password)
    setFormError(problem)
    if (!problem) mutation.mutate()
  }

  function switchMode(next: Mode) {
    setMode(next)
    setFormError(null)
    mutation.reset()
  }

  const serverError = mutation.error instanceof ApiRequestError ? mutation.error.message : mutation.error ? 'Something went wrong. Please try again.' : null
  const error = formError ?? serverError

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-700 text-lg font-semibold text-white shadow-sm">
            S
          </div>
          <h1 className="mt-3 text-xl font-semibold tracking-tight text-slate-900">Sheet2Portal</h1>
          <p className="mt-1 text-sm text-slate-500">
            {mode === 'login' ? 'Sign in to your portals' : 'Create an account to turn workbooks into portals'}
          </p>
        </div>

        <div className="panel p-6">
          <div className="mb-5 grid grid-cols-2 rounded-lg bg-slate-100 p-1 text-sm font-medium" role="tablist">
            {(['login', 'signup'] as const).map((m) => (
              <button
                key={m}
                role="tab"
                aria-selected={mode === m}
                type="button"
                onClick={() => switchMode(m)}
                className={`rounded-md py-1.5 transition-colors ${mode === m ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
              >
                {m === 'login' ? 'Sign in' : 'Sign up'}
              </button>
            ))}
          </div>

          <form onSubmit={submit} noValidate className="space-y-4">
            {mode === 'signup' && (
              <label className="block">
                <span className="text-sm font-medium text-slate-700">Name</span>
                <input
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  autoComplete="name"
                  maxLength={80}
                  placeholder="Optional"
                  className="input mt-1 w-full"
                />
              </label>
            )}
            <label className="block">
              <span className="text-sm font-medium text-slate-700">Email</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
                className="input mt-1 w-full"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-slate-700">Password</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                required
                className="input mt-1 w-full"
              />
              {mode === 'signup' && (
                <span className="mt-1 block text-xs text-slate-500">At least 8 characters, with a letter and a number.</span>
              )}
            </label>

            {error && (
              <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={mutation.isPending}
              className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700 disabled:opacity-60"
            >
              {mutation.isPending ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
