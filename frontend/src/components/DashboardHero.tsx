import { useReducer } from 'react'
import type { PortalConfig } from '../types/portal'
import {
  backgroundSrc,
  backgroundSrcSet,
  nextImageStatus,
  resolveBackground,
  shouldRenderImage,
  type BackgroundTheme,
} from '../lib/backgrounds'

// Main content column is max-w-7xl minus padding, so the banner never needs
// more than ~1232 CSS px; the browser picks a width from the srcset.
const SIZES = '(min-width: 1280px) 1232px, calc(100vw - 2rem)'

function HeroImage({ theme }: { theme: BackgroundTheme }) {
  const [status, dispatch] = useReducer(nextImageStatus, 'loading')
  if (!shouldRenderImage(theme, status)) return null
  return (
    <img
      src={backgroundSrc(theme, 1280)}
      srcSet={backgroundSrcSet(theme)}
      sizes={SIZES}
      alt={theme.alt}
      // Above the fold on the dashboard, so load eagerly with high priority
      // rather than lazily -- it's the page's largest image.
      loading="eager"
      fetchPriority="high"
      decoding="async"
      onLoad={() => dispatch('load')}
      onError={() => dispatch('error')}
      style={{ objectPosition: theme.focus }}
      className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-700 ${status === 'loaded' ? 'opacity-100' : 'opacity-0'}`}
    />
  )
}

export function DashboardHero({ config, backgroundOverride }: { config: PortalConfig; backgroundOverride?: string | null }) {
  const theme = resolveBackground(config.domain, backgroundOverride)
  // Business sheets only -- README / data-dictionary sheets aren't records.
  const business = config.entities.filter((e) => !e.reference)
  const totalRecords = business.reduce((sum, e) => sum + e.row_count, 0)

  return (
    <section
      aria-label={`${config.title} overview`}
      className="relative isolate overflow-hidden rounded-2xl shadow-sm ring-1 ring-slate-900/5"
      style={{ backgroundImage: theme.fallbackGradient }}
    >
      {/* key: reset the load state when the theme changes */}
      <HeroImage key={theme.domain} theme={theme} />
      {/* Readability: a dark wash weighted to the text side, plus a bottom fade. */}
      <div className="absolute inset-0 bg-gradient-to-r from-slate-950/85 via-slate-950/55 to-slate-950/15" aria-hidden />
      <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-slate-950/50 to-transparent" aria-hidden />

      <div className="relative flex min-h-44 flex-col justify-end gap-3 px-5 py-6 sm:min-h-52 sm:px-8 sm:py-8 lg:min-h-60">
        <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-white/15 px-2.5 py-1 text-xs font-medium text-white ring-1 ring-white/25 backdrop-blur-sm">
          <span className="h-1.5 w-1.5 rounded-full bg-indigo-300" aria-hidden />
          {theme.label}
        </span>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-white drop-shadow-sm sm:text-3xl">{config.title}</h1>
          <p className="mt-1 text-sm text-slate-200">
            {business.length} {business.length === 1 ? 'worksheet' : 'worksheets'} ·{' '}
            {totalRecords.toLocaleString()} records · live from your workbook
          </p>
        </div>
      </div>

      {theme.credit && (
        <a
          href={theme.credit.url}
          target="_blank"
          rel="noreferrer"
          className="absolute right-3 bottom-2 text-[10px] text-white/60 hover:text-white/90 hover:underline"
        >
          {theme.credit.text}
        </a>
      )}
    </section>
  )
}
