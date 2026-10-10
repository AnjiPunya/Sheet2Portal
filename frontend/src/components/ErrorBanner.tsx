interface Props {
  code: string
  message: string
  variant?: 'error' | 'warning'
}

const STYLES: Record<string, string> = {
  error: 'border-red-200 bg-red-50 text-red-800',
  warning: 'border-amber-200 bg-amber-50 text-amber-800',
}

export function ErrorBanner({ code, message, variant = 'error' }: Props) {
  return (
    <div className={`rounded-lg border p-4 ${STYLES[variant]}`}>
      <p className="font-medium">{code.replaceAll('_', ' ')}</p>
      <p className="text-sm opacity-80">{message}</p>
    </div>
  )
}
