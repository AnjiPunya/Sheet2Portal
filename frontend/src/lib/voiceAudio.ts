// Pure helpers for the voice assistant (no React, no DOM globals) so they can
// be unit-tested with `node --test`.

export type LanguageMode = 'auto' | 'te' | 'en'

export const LANGUAGE_MODE_OPTIONS: { value: LanguageMode; label: string; hint: string }[] = [
  { value: 'auto', label: 'Auto', hint: 'Telugu, English or mixed' },
  { value: 'te', label: 'తెలుగు', hint: 'Telugu' },
  { value: 'en', label: 'English', hint: 'English' },
]

// Preferred first. Chrome/Firefox/Edge record webm/opus; Safari only mp4/aac.
const RECORDER_MIME_TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']

export function pickRecorderMimeType(isTypeSupported: (type: string) => boolean): string | undefined {
  return RECORDER_MIME_TYPES.find((type) => {
    try {
      return isTypeSupported(type)
    } catch {
      return false
    }
  })
}

export function fileExtensionFor(mimeType: string): string {
  if (mimeType.includes('webm')) return 'webm'
  if (mimeType.includes('ogg')) return 'ogg'
  if (mimeType.includes('mp4') || mimeType.includes('aac')) return 'm4a'
  if (mimeType.includes('wav')) return 'wav'
  return 'webm'
}

/** Root-mean-square level of a time-domain sample buffer in [-1, 1]. */
export function rmsLevel(samples: ArrayLike<number>): number {
  if (samples.length === 0) return 0
  let sum = 0
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i]
  return Math.sqrt(sum / samples.length)
}

export type SilenceVerdict = 'continue' | 'stop' | 'no-speech' | 'max-duration'

export interface SilenceDetectorOptions {
  silenceMs?: number // stop after this much quiet once speech was heard
  noSpeechMs?: number // give up if nothing is heard at all for this long
  maxMs?: number // hard cap on recording length
  minThreshold?: number // absolute floor for the speech threshold
  calibrationMs?: number // initial window used to measure background noise
}

/**
 * Voice-activity state machine fed with (level, timestamp) samples. The
 * speech threshold adapts to the measured background noise so a noisy room
 * doesn't keep the recording open forever.
 */
export class SilenceDetector {
  private readonly silenceMs: number
  private readonly noSpeechMs: number
  private readonly maxMs: number
  private readonly minThreshold: number
  private readonly calibrationMs: number
  private startedAt: number | null = null
  private lastVoiceAt: number | null = null
  private speechMs = 0
  private lastSampleAt: number | null = null
  private noiseSum = 0
  private noiseCount = 0

  constructor(options: SilenceDetectorOptions = {}) {
    this.silenceMs = options.silenceMs ?? 1600
    this.noSpeechMs = options.noSpeechMs ?? 8000
    this.maxMs = options.maxMs ?? 60000
    this.minThreshold = options.minThreshold ?? 0.02
    this.calibrationMs = options.calibrationMs ?? 300
  }

  get threshold(): number {
    const floor = this.noiseCount ? this.noiseSum / this.noiseCount : 0
    return Math.max(this.minThreshold, floor * 2.5)
  }

  get heardSpeech(): boolean {
    return this.speechMs >= 200
  }

  feed(level: number, now: number): SilenceVerdict {
    if (this.startedAt === null) this.startedAt = now
    const elapsed = now - this.startedAt
    const dt = this.lastSampleAt === null ? 0 : now - this.lastSampleAt
    this.lastSampleAt = now

    if (elapsed >= this.maxMs) return 'max-duration'
    if (elapsed < this.calibrationMs) {
      this.noiseSum += level
      this.noiseCount += 1
      return 'continue'
    }
    if (level >= this.threshold) {
      this.speechMs += dt
      this.lastVoiceAt = now
      return 'continue'
    }
    if (this.heardSpeech && this.lastVoiceAt !== null && now - this.lastVoiceAt >= this.silenceMs) return 'stop'
    if (!this.heardSpeech && elapsed >= this.noSpeechMs) return 'no-speech'
    return 'continue'
  }
}

export interface VoiceLike {
  lang: string
  name: string
  localService?: boolean
}

const normaliseLang = (lang: string) => lang.replace('_', '-').toLowerCase()

/**
 * Best speechSynthesis voice for a BCP-47 tag ("te-IN" / "en-IN"), or null.
 * Telugu replies must not fall back to a non-Telugu voice (it would read
 * Telugu script as silence or gibberish), so only English widens to any en-*.
 */
export function pickVoice<T extends VoiceLike>(voices: readonly T[], lang: string): T | null {
  const want = normaliseLang(lang)
  const base = want.split('-')[0]
  const quality = (v: T) => (/natural|neural|online|google|premium|enhanced/i.test(v.name) ? 1 : 0)
  const ranked = (list: T[]) => [...list].sort((a, b) => quality(b) - quality(a))[0] ?? null

  const exact = voices.filter((v) => normaliseLang(v.lang) === want)
  if (exact.length) return ranked(exact)
  const sameLanguage = voices.filter((v) => normaliseLang(v.lang).split('-')[0] === base)
  if (sameLanguage.length) {
    if (base === 'en') {
      const preferred = ['en-in', 'en-gb', 'en-us']
      for (const tag of preferred) {
        const match = sameLanguage.filter((v) => normaliseLang(v.lang) === tag)
        if (match.length) return ranked(match)
      }
    }
    return ranked(sameLanguage)
  }
  return null
}

/** Split speakable text into short utterances: Chrome silently cuts off long ones. */
export function chunkForSpeech(text: string, maxChars = 180): string[] {
  const sentences = text.match(/[^.!?।]+[.!?।]*\s*/g) ?? [text]
  const chunks: string[] = []
  let current = ''
  for (const raw of sentences) {
    const sentence = raw.trim()
    if (!sentence) continue
    if (sentence.length > maxChars) {
      if (current) chunks.push(current)
      current = ''
      let rest = sentence
      while (rest.length > maxChars) {
        const cut = rest.lastIndexOf(' ', maxChars)
        const at = cut > maxChars / 2 ? cut : maxChars
        chunks.push(rest.slice(0, at).trim())
        rest = rest.slice(at).trim()
      }
      current = rest
      continue
    }
    if ((current + ' ' + sentence).trim().length > maxChars) {
      chunks.push(current)
      current = sentence
    } else {
      current = (current + ' ' + sentence).trim()
    }
  }
  if (current) chunks.push(current)
  return chunks
}

export type MicUnavailableReason = 'insecure-context' | 'no-media-devices' | 'no-media-recorder' | null

export function micUnavailableReason(env: {
  isSecureContext: boolean
  hasGetUserMedia: boolean
  hasMediaRecorder: boolean
}): MicUnavailableReason {
  if (!env.isSecureContext) return 'insecure-context'
  if (!env.hasGetUserMedia) return 'no-media-devices'
  if (!env.hasMediaRecorder) return 'no-media-recorder'
  return null
}

export function micErrorMessage(error: unknown): string {
  const name = error instanceof Error || (typeof error === 'object' && error && 'name' in error) ? String((error as { name: string }).name) : ''
  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return 'Microphone access was blocked. Allow the microphone for this site in your browser settings, then try again.'
    case 'NotFoundError':
    case 'OverconstrainedError':
      return 'No microphone was found. Connect one and try again.'
    case 'NotReadableError':
    case 'AbortError':
      return 'The microphone is in use by another app or could not be started.'
    default:
      return 'Could not start the microphone.'
  }
}

export const UNAVAILABLE_MESSAGES: Record<Exclude<MicUnavailableReason, null>, string> = {
  'insecure-context': 'Voice input needs a secure page (HTTPS or localhost).',
  'no-media-devices': 'This browser does not allow microphone access.',
  'no-media-recorder': 'This browser cannot record audio. Try a recent Chrome, Edge, Firefox or Safari.',
}
