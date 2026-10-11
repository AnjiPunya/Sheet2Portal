import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync, statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import {
  BACKGROUNDS,
  BACKGROUND_WIDTHS,
  GENERIC_DOMAIN,
  backgroundSrc,
  backgroundSrcSet,
  nextImageStatus,
  resolveBackground,
  shouldRenderImage,
  type BackgroundTheme,
} from '../src/lib/backgrounds.ts'

const PUBLIC_DIR = fileURLToPath(new URL('../public', import.meta.url))
const BACKEND_DOMAIN_MODULE = fileURLToPath(new URL('../../backend/app/services/analysis/domain.py', import.meta.url))

// --- mapping ---------------------------------------------------------------

test('each detected domain maps to its own banner', () => {
  for (const domain of ['construction', 'aquaculture', 'retail', 'agriculture', 'healthcare']) {
    const theme = resolveBackground(domain)
    assert.equal(theme.domain, domain)
    assert.equal(backgroundSrc(theme, 1280), `/backgrounds/${domain}-1280.jpg`)
  }
})

test('unknown, missing and generic domains fall back to the generic banner', () => {
  for (const domain of ['shipping', '', null, undefined, 'generic']) {
    assert.equal(resolveBackground(domain).domain, GENERIC_DOMAIN, String(domain))
  }
})

test('an explicit background choice overrides the detected domain', () => {
  assert.equal(resolveBackground('retail', 'aquaculture').domain, 'aquaculture')
  // An unknown override is ignored rather than breaking the banner.
  assert.equal(resolveBackground('retail', 'no-such-theme').domain, 'retail')
})

test('srcset lists every exported width', () => {
  const srcset = backgroundSrcSet(resolveBackground('retail'))
  assert.equal(
    srcset,
    BACKGROUND_WIDTHS.map((w) => `/backgrounds/retail-${w}.jpg ${w}w`).join(', '),
  )
})

test('every backend-detectable domain has a banner (registries stay in sync)', () => {
  const source = readFileSync(BACKEND_DOMAIN_MODULE, 'utf8')
  const block = source.slice(source.indexOf('DOMAIN_KEYWORDS'), source.indexOf('\n}\n', source.indexOf('DOMAIN_KEYWORDS')))
  const backendDomains = [...block.matchAll(/^ {4}"([a-z_]+)": \(/gm)].map((m) => m[1])
  assert.ok(backendDomains.length >= 5, `parsed ${backendDomains.join(',')}`)
  for (const domain of backendDomains) {
    assert.ok(BACKGROUNDS[domain], `no banner for backend domain "${domain}"`)
  }
})

// --- assets ----------------------------------------------------------------

test('every referenced image exists locally, in every width, and is reasonably small', () => {
  for (const theme of Object.values(BACKGROUNDS)) {
    for (const width of BACKGROUND_WIDTHS) {
      const src = backgroundSrc(theme, width)
      assert.ok(src, theme.domain)
      const file = `${PUBLIC_DIR}${src}`
      assert.ok(existsSync(file), `missing ${file}`)
      assert.ok(statSync(file).size < 300 * 1024, `${src} is over 300 KB`)
    }
  }
})

test('images whose license requires attribution carry a credit', () => {
  const credits = readFileSync(`${PUBLIC_DIR}/backgrounds/CREDITS.md`, 'utf8')
  for (const theme of Object.values(BACKGROUNDS)) {
    assert.ok(credits.includes(`\`${theme.image}-*.jpg\``), `${theme.domain} missing from CREDITS.md`)
  }
  assert.ok(BACKGROUNDS.aquaculture.credit?.text.includes('CC BY 2.0'))
})

test('every theme has alt text and a fallback gradient', () => {
  for (const theme of Object.values(BACKGROUNDS)) {
    assert.ok(theme.alt.length > 10, theme.domain)
    assert.match(theme.fallbackGradient, /^linear-gradient\(/, theme.domain)
  }
})

// --- image-loading fallback ------------------------------------------------

test('a successful load shows the photo', () => {
  assert.equal(nextImageStatus('loading', 'load'), 'loaded')
  assert.equal(shouldRenderImage(resolveBackground('retail'), 'loaded'), true)
})

test('a failed load removes the photo, leaving the gradient fallback', () => {
  const status = nextImageStatus('loading', 'error')
  assert.equal(status, 'failed')
  assert.equal(shouldRenderImage(resolveBackground('retail'), status), false)
})

test('a late load event after an error does not bring a broken image back', () => {
  assert.equal(nextImageStatus('failed', 'load'), 'failed')
})

test('changing theme resets the loading state', () => {
  assert.equal(nextImageStatus('failed', 'reset'), 'loading')
})

test('a theme without an image renders gradient only', () => {
  const gradientOnly: BackgroundTheme = { ...BACKGROUNDS[GENERIC_DOMAIN], image: undefined }
  assert.equal(shouldRenderImage(gradientOnly, 'loading'), false)
  assert.equal(backgroundSrcSet(gradientOnly), undefined)
})
