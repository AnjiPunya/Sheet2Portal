// Central registry: business domain (detected deterministically by the
// backend, see backend/app/services/analysis/domain.py) -> dashboard banner.
// Components never hardcode image URLs -- they call resolveBackground().
// Images are local static files in frontend/public/backgrounds (sources and
// licenses in CREDITS.md there), so the portal never depends on an external
// image host. Kept free of React/browser imports so it can be unit-tested.

export interface BackgroundCredit {
  text: string
  url: string
}

export interface BackgroundTheme {
  /** Domain key, matching the backend's PortalConfig.domain. */
  domain: string
  /** Human label shown on the banner, e.g. "Real Estate & Construction". */
  label: string
  /** File stem in /backgrounds: `${image}-${width}.jpg`. Omit for gradient-only. */
  image?: string
  /** Describes the photo for screen readers. */
  alt: string
  /** CSS object-position, so the subject survives responsive cropping. */
  focus: string
  /** Shown if the image is missing or fails to load (and under it while loading). */
  fallbackGradient: string
  /** Required when the image license needs attribution (e.g. CC BY). */
  credit?: BackgroundCredit
}

/** Widths each image is exported at (see public/backgrounds). */
export const BACKGROUND_WIDTHS = [768, 1280, 1600] as const

export const GENERIC_DOMAIN = 'generic'

export const BACKGROUNDS: Record<string, BackgroundTheme> = {
  construction: {
    domain: 'construction',
    label: 'Real Estate & Construction',
    image: 'construction',
    alt: 'Engineers in hard hats on a concrete slab at a construction site',
    focus: '60% 70%',
    fallbackGradient: 'linear-gradient(135deg, #78350f 0%, #b45309 45%, #1e293b 100%)',
  },
  aquaculture: {
    domain: 'aquaculture',
    label: 'Aquaculture',
    image: 'aquaculture',
    alt: 'Aerial view of rectangular fish farming ponds',
    focus: '50% 50%',
    fallbackGradient: 'linear-gradient(135deg, #134e4a 0%, #0f766e 45%, #0c4a6e 100%)',
    credit: {
      text: 'Photo: U.S. Department of Agriculture, CC BY 2.0',
      url: 'https://commons.wikimedia.org/wiki/File:Louisiana_Catfish_Ponds_k4724-7.jpg',
    },
  },
  retail: {
    domain: 'retail',
    label: 'Retail & Inventory',
    image: 'retail',
    alt: 'Supermarket aisle lined with stocked product shelves',
    focus: '50% 45%',
    fallbackGradient: 'linear-gradient(135deg, #7c2d12 0%, #c2410c 45%, #312e81 100%)',
  },
  agriculture: {
    domain: 'agriculture',
    label: 'Agriculture',
    image: 'agriculture',
    alt: 'Farm field at sunrise',
    focus: '50% 60%',
    fallbackGradient: 'linear-gradient(135deg, #365314 0%, #4d7c0f 45%, #713f12 100%)',
  },
  healthcare: {
    domain: 'healthcare',
    label: 'Healthcare',
    image: 'healthcare',
    alt: 'Clean hospital ward with beds',
    focus: '50% 50%',
    fallbackGradient: 'linear-gradient(135deg, #0c4a6e 0%, #0369a1 45%, #1e3a8a 100%)',
  },
  [GENERIC_DOMAIN]: {
    domain: GENERIC_DOMAIN,
    label: 'Business Portal',
    image: 'generic',
    alt: 'Modern office towers seen from below',
    focus: '50% 40%',
    fallbackGradient: 'linear-gradient(135deg, #312e81 0%, #4338ca 45%, #0f172a 100%)',
  },
}

/** The theme for a domain. Unknown/missing domains fall back to generic.
 * `override` lets a user-chosen background (a future setting) win over the
 * detected domain without any other code changing. */
export function resolveBackground(domain: string | null | undefined, override?: string | null): BackgroundTheme {
  return BACKGROUNDS[override ?? ''] ?? BACKGROUNDS[domain ?? ''] ?? BACKGROUNDS[GENERIC_DOMAIN]
}

export function backgroundSrc(theme: BackgroundTheme, width: number): string | undefined {
  return theme.image ? `/backgrounds/${theme.image}-${width}.jpg` : undefined
}

/** `srcset` for responsive loading; the browser picks the smallest adequate width. */
export function backgroundSrcSet(theme: BackgroundTheme): string | undefined {
  if (!theme.image) return undefined
  return BACKGROUND_WIDTHS.map((w) => `${backgroundSrc(theme, w)} ${w}w`).join(', ')
}

// Image loading state for the banner: the gradient always renders, the photo
// fades in on load, and a failed load leaves just the gradient.
export type ImageStatus = 'loading' | 'loaded' | 'failed'
export type ImageEvent = 'load' | 'error' | 'reset'

export function nextImageStatus(status: ImageStatus, event: ImageEvent): ImageStatus {
  if (event === 'reset') return 'loading'
  if (status === 'failed') return 'failed' // a late 'load' after an error must not resurrect it
  return event === 'load' ? 'loaded' : 'failed'
}

/** Whether to render the <img> at all (no image configured, or it failed). */
export function shouldRenderImage(theme: BackgroundTheme, status: ImageStatus): boolean {
  return !!theme.image && status !== 'failed'
}
