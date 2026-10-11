import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  SilenceDetector,
  chunkForSpeech,
  fileExtensionFor,
  micErrorMessage,
  micUnavailableReason,
  pickRecorderMimeType,
  pickVoice,
  rmsLevel,
} from '../src/lib/voiceAudio.ts'

test('pickRecorderMimeType prefers webm/opus and falls back to mp4 (Safari)', () => {
  assert.equal(pickRecorderMimeType(() => true), 'audio/webm;codecs=opus')
  assert.equal(pickRecorderMimeType((t) => t === 'audio/mp4'), 'audio/mp4')
  assert.equal(pickRecorderMimeType(() => false), undefined)
  assert.equal(
    pickRecorderMimeType(() => {
      throw new Error('boom')
    }),
    undefined,
  )
})

test('fileExtensionFor maps recorder mime types', () => {
  assert.equal(fileExtensionFor('audio/webm;codecs=opus'), 'webm')
  assert.equal(fileExtensionFor('audio/mp4'), 'm4a')
  assert.equal(fileExtensionFor('audio/ogg;codecs=opus'), 'ogg')
})

test('rmsLevel', () => {
  assert.equal(rmsLevel([]), 0)
  assert.equal(rmsLevel([0.5, -0.5, 0.5, -0.5]), 0.5)
})

function run(detector: SilenceDetector, samples: [number, number][]) {
  // samples: [level, durationMs] fed every 50ms
  let t = 0
  let verdict = 'continue'
  for (const [level, duration] of samples) {
    for (let elapsed = 0; elapsed < duration; elapsed += 50) {
      verdict = detector.feed(level, t)
      t += 50
      if (verdict !== 'continue') return { verdict, t }
    }
  }
  return { verdict, t }
}

test('SilenceDetector stops after a pause following speech', () => {
  const r = run(new SilenceDetector({ silenceMs: 1000 }), [
    [0.005, 300],
    [0.2, 1500],
    [0.005, 3000],
  ])
  assert.equal(r.verdict, 'stop')
  assert.ok(r.t >= 2800 && r.t <= 3000, `stopped at ${r.t}`)
})

test('SilenceDetector reports no-speech when nothing is said', () => {
  const r = run(new SilenceDetector({ noSpeechMs: 2000 }), [[0.004, 5000]])
  assert.equal(r.verdict, 'no-speech')
})

test('SilenceDetector adapts its threshold to background noise', () => {
  const d = new SilenceDetector({ silenceMs: 1000, noSpeechMs: 3000 })
  // Constant fan noise at 0.03 (above the 0.02 floor) must not count as speech.
  const r = run(d, [[0.03, 5000]])
  assert.equal(r.verdict, 'no-speech')
  assert.ok(d.threshold >= 0.07 && d.threshold <= 0.075 + 1e-9)
})

test('SilenceDetector still hears a user who starts talking immediately', () => {
  // Speech during the 300ms calibration window must not raise the threshold above the speech itself.
  const d = new SilenceDetector({ silenceMs: 1000 })
  const r = run(d, [
    [0.12, 2000],
    [0.004, 3000],
  ])
  assert.equal(r.verdict, 'stop')
  assert.ok(d.heardSpeech)
})

test('SilenceDetector enforces the max duration', () => {
  const r = run(new SilenceDetector({ maxMs: 2000 }), [[0.3, 10000]])
  assert.equal(r.verdict, 'max-duration')
})

const VOICES = [
  { lang: 'en-US', name: 'Samantha' },
  { lang: 'en-GB', name: 'Daniel' },
  { lang: 'hi-IN', name: 'Lekha' },
  { lang: 'te_IN', name: 'Telugu basic' },
  { lang: 'te-IN', name: 'Microsoft Shruti Online (Natural) - Telugu (India)' },
]

test('pickVoice picks the best Telugu voice and never a non-Telugu one for te-IN', () => {
  assert.equal(pickVoice(VOICES, 'te-IN')?.name, 'Microsoft Shruti Online (Natural) - Telugu (India)')
  assert.equal(pickVoice(VOICES.filter((v) => !v.lang.startsWith('te')), 'te-IN'), null)
})

test('pickVoice widens English to en-GB/en-US when en-IN is missing', () => {
  assert.equal(pickVoice(VOICES, 'en-IN')?.lang, 'en-GB')
  assert.equal(pickVoice([{ lang: 'en-IN', name: 'Rishi' }, ...VOICES], 'en-IN')?.name, 'Rishi')
})

test('chunkForSpeech keeps sentences together and splits long text', () => {
  assert.deepEqual(chunkForSpeech('మొత్తం 35000. Pending tasks 2.', 180), ['మొత్తం 35000. Pending tasks 2.'])
  const chunks = chunkForSpeech('word '.repeat(100), 50)
  assert.ok(chunks.length > 5)
  assert.ok(chunks.every((c) => c.length <= 50))
  assert.equal(chunks.join(' ').split(/\s+/).length, 100)
})

test('micUnavailableReason checks secure context first', () => {
  assert.equal(micUnavailableReason({ isSecureContext: false, hasGetUserMedia: true, hasMediaRecorder: true }), 'insecure-context')
  assert.equal(micUnavailableReason({ isSecureContext: true, hasGetUserMedia: false, hasMediaRecorder: true }), 'no-media-devices')
  assert.equal(micUnavailableReason({ isSecureContext: true, hasGetUserMedia: true, hasMediaRecorder: false }), 'no-media-recorder')
  assert.equal(micUnavailableReason({ isSecureContext: true, hasGetUserMedia: true, hasMediaRecorder: true }), null)
})

test('micErrorMessage explains permission denial', () => {
  assert.match(micErrorMessage({ name: 'NotAllowedError' }), /blocked/)
  assert.match(micErrorMessage({ name: 'NotFoundError' }), /No microphone/)
  assert.match(micErrorMessage(new Error('x')), /Could not start/)
})
