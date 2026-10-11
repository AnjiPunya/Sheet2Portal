import { test } from 'node:test'
import assert from 'node:assert/strict'
import { SilenceDetector, type SilenceVerdict } from '../src/lib/voiceAudio.ts'
import {
  MAX_CONSECUTIVE_FAILURES,
  classifyVoiceError,
  initialSession,
  sessionReducer,
  type SessionEvent,
  type SessionState,
} from '../src/lib/voiceSession.ts'

const run = (events: SessionEvent[], from: SessionState = initialSession) => events.reduce(sessionReducer, from)

// --- Pauses: one detector per utterance, fed 50 ms level samples ----------

/** Feed [level, ms] segments; returns the verdict that ended the clip and when. */
function feedTimeline(detector: SilenceDetector, segments: [number, number][]): { verdict: SilenceVerdict; at: number } {
  let now = 0
  for (const [level, ms] of segments) {
    for (let t = 0; t < ms; t += 50) {
      const verdict = detector.feed(level, now)
      if (verdict !== 'continue') return { verdict, at: now }
      now += 50
    }
  }
  return { verdict: 'continue', at: now }
}

const QUIET = 0.005
const VOICE = 0.2

test('a short pause mid-sentence does not cut the utterance; a longer one ends it', () => {
  const detector = new SilenceDetector()
  const { verdict, at } = feedTimeline(detector, [
    [QUIET, 300], // calibration
    [VOICE, 1200], // "ఈ నెల budget ఎంత,"
    [QUIET, 900], // thinking pause, shorter than the 1.6 s cut-off
    [VOICE, 800], // "and how much spent?"
    [QUIET, 3000],
  ])
  assert.equal(verdict, 'stop')
  // Ends ~1.6 s after the *second* phrase, not during the first pause.
  assert.ok(at > 300 + 1200 + 900 + 800, `stopped too early at ${at}ms`)
  assert.ok(at <= 300 + 1200 + 900 + 800 + 1700)
})

test('a long quiet stretch with no speech reports no-speech (session keeps listening)', () => {
  const detector = new SilenceDetector()
  const { verdict } = feedTimeline(detector, [[QUIET, 10000]])
  assert.equal(verdict, 'no-speech')
  assert.equal(detector.heardSpeech, false)
})

// --- Session state machine -------------------------------------------------

test('start begins listening; a captured utterance moves to processing', () => {
  const listening = run([{ type: 'start' }])
  assert.equal(listening.phase, 'listening')
  assert.equal(run([{ type: 'utterance' }], listening).phase, 'processing')
})

test('after a spoken reply ends, listening resumes automatically (after the echo delay)', () => {
  const s = run([{ type: 'start' }, { type: 'utterance' }, { type: 'reply', speak: true }])
  assert.equal(s.phase, 'speaking')
  const resumed = sessionReducer(s, { type: 'speech-ended' })
  assert.equal(resumed.phase, 'listening')
  assert.equal(resumed.afterSpeech, true)
  assert.ok(resumed.listenId > s.listenId, 'listenId must change so the recorder re-arms')
})

test('muted replies go straight back to listening', () => {
  const s = run([{ type: 'start' }, { type: 'utterance' }, { type: 'reply', speak: false }])
  assert.equal(s.phase, 'listening')
  assert.equal(s.afterSpeech, false)
})

test('multiple back-to-back questions keep the session alive and re-arm each time', () => {
  let s = run([{ type: 'start' }])
  const ids = [s.listenId]
  for (let i = 0; i < 5; i++) {
    s = run([{ type: 'utterance' }, { type: 'reply', speak: i % 2 === 0 }, ...(i % 2 === 0 ? [{ type: 'speech-ended' } as const] : [])], s)
    assert.equal(s.phase, 'listening', `turn ${i}`)
    ids.push(s.listenId)
  }
  assert.equal(new Set(ids).size, ids.length, 'every turn gets a fresh listenId')
})

test('silence or an unusable clip keeps listening without counting as a failure', () => {
  const s = run([{ type: 'start' }, { type: 'no-speech' }, { type: 'no-speech' }])
  assert.equal(s.phase, 'listening')
  assert.equal(s.failures, 0)
  // Server said NO_SPEECH_DETECTED while processing: back to listening.
  assert.equal(run([{ type: 'utterance' }, { type: 'no-speech' }], s).phase, 'listening')
})

test('interrupting a spoken reply or a pending request resumes listening', () => {
  const speaking = run([{ type: 'start' }, { type: 'utterance' }, { type: 'reply', speak: true }])
  const a = sessionReducer(speaking, { type: 'interrupt' })
  assert.equal(a.phase, 'listening')
  assert.equal(a.afterSpeech, false)
  // speech.stop() then fires speech-ended for the cut-off reply: must be ignored.
  assert.deepEqual(sessionReducer(a, { type: 'speech-ended' }), a)

  const processing = run([{ type: 'start' }, { type: 'utterance' }])
  const b = sessionReducer(processing, { type: 'interrupt' })
  assert.equal(b.phase, 'listening')
  // The aborted request's late reply is ignored.
  assert.deepEqual(sessionReducer(b, { type: 'reply', speak: true }), b)
})

test('interrupt while already listening is a no-op', () => {
  const s = run([{ type: 'start' }])
  assert.deepEqual(sessionReducer(s, { type: 'interrupt' }), s)
})

test('explicit stop ends the session from any phase, and late events cannot revive it', () => {
  const phases: SessionEvent[][] = [
    [{ type: 'start' }],
    [{ type: 'start' }, { type: 'utterance' }],
    [{ type: 'start' }, { type: 'utterance' }, { type: 'reply', speak: true }],
  ]
  for (const events of phases) {
    const stopped = run([...events, { type: 'stop' }])
    assert.equal(stopped.phase, 'off')
    for (const late of [
      { type: 'utterance' },
      { type: 'reply', speak: true },
      { type: 'speech-ended' },
      { type: 'no-speech' },
      { type: 'interrupt' },
      { type: 'error', fatal: false },
    ] as SessionEvent[]) {
      assert.equal(sessionReducer(stopped, late).phase, 'off', `late ${late.type} revived the session`)
    }
  }
})

test('a recoverable error keeps listening; repeated failures end the session', () => {
  let s = run([{ type: 'start' }])
  for (let i = 1; i < MAX_CONSECUTIVE_FAILURES; i++) {
    s = run([{ type: 'utterance' }, { type: 'error', fatal: false }], s)
    assert.equal(s.phase, 'listening')
    assert.equal(s.failures, i)
  }
  s = run([{ type: 'utterance' }, { type: 'error', fatal: false }], s)
  assert.equal(s.phase, 'off')
})

test('a successful reply resets the failure count', () => {
  const s = run([
    { type: 'start' },
    { type: 'utterance' },
    { type: 'error', fatal: false },
    { type: 'utterance' },
    { type: 'reply', speak: false },
  ])
  assert.equal(s.failures, 0)
})

test('a fatal error (mic lost, permission denied, not configured) ends the session', () => {
  assert.equal(run([{ type: 'start' }, { type: 'error', fatal: true }]).phase, 'off')
})

test('restarting after a stop clears the failure count', () => {
  const s = run([{ type: 'start' }, { type: 'utterance' }, { type: 'error', fatal: false }, { type: 'stop' }, { type: 'start' }])
  assert.equal(s.phase, 'listening')
  assert.equal(s.failures, 0)
})

test('classifyVoiceError: silent, fatal and retryable server errors', () => {
  assert.equal(classifyVoiceError('NO_SPEECH_DETECTED'), 'silent')
  assert.equal(classifyVoiceError('EMPTY_AUDIO'), 'silent')
  for (const code of ['VOICE_NOT_CONFIGURED', 'PROVIDER_AUTH_FAILED', 'PROVIDER_QUOTA_EXHAUSTED', 'NOT_FOUND', 'NOT_AUTHENTICATED', 'SESSION_EXPIRED']) {
    assert.equal(classifyVoiceError(code), 'fatal', code)
  }
  for (const code of ['PROVIDER_RATE_LIMITED', 'PROVIDER_TIMEOUT', 'PROVIDER_UNAVAILABLE', 'AUDIO_UNREADABLE', 'UNKNOWN_ERROR']) {
    assert.equal(classifyVoiceError(code), 'retry', code)
  }
  assert.equal(classifyVoiceError(null), 'retry') // network failure (no API error)
})

// --- End-to-end loop with a simulated mic, network and speaker ----------

test('simulated conversation: Telugu, English and mixed questions with pauses, interruption, then stop', () => {
  // Each turn: what the mic hears, and how the "server" and "speaker" respond.
  type Turn = { speech: [number, number][]; outcome: 'reply' | 'silence' | 'rate-limited' | 'interrupt' }
  const turns: Turn[] = [
    { speech: [[QUIET, 300], [VOICE, 1500], [QUIET, 2000]], outcome: 'reply' }, // Telugu
    { speech: [[QUIET, 9000]], outcome: 'silence' }, // user says nothing for a while
    { speech: [[QUIET, 300], [VOICE, 700], [QUIET, 600], [VOICE, 900], [QUIET, 2000]], outcome: 'reply' }, // mixed, mid-pause
    { speech: [[QUIET, 300], [VOICE, 1000], [QUIET, 2000]], outcome: 'rate-limited' }, // English, 429
    { speech: [[QUIET, 300], [VOICE, 1000], [QUIET, 2000]], outcome: 'interrupt' }, // user skips the reply
    { speech: [[QUIET, 300], [VOICE, 1000], [QUIET, 2000]], outcome: 'reply' }, // follow-up
  ]
  let s = sessionReducer(initialSession, { type: 'start' })
  let uploads = 0
  let recorderOpenWhileSpeaking = false
  for (const turn of turns) {
    assert.equal(s.phase, 'listening')
    const { verdict } = feedTimeline(new SilenceDetector(), turn.speech)
    if (verdict === 'no-speech') {
      s = sessionReducer(s, { type: 'no-speech' })
      continue
    }
    assert.equal(verdict, 'stop')
    uploads++
    s = sessionReducer(s, { type: 'utterance' })
    if (turn.outcome === 'rate-limited') {
      s = sessionReducer(s, { type: 'error', fatal: classifyVoiceError('PROVIDER_RATE_LIMITED') === 'fatal' })
      continue
    }
    s = sessionReducer(s, { type: 'reply', speak: true })
    // Half-duplex: the recorder only runs in `listening`, never while speaking.
    recorderOpenWhileSpeaking ||= s.phase === 'listening'
    if (turn.outcome === 'interrupt') {
      s = sessionReducer(s, { type: 'interrupt' })
      s = sessionReducer(s, { type: 'speech-ended' }) // fired by speech.stop(); ignored
    } else {
      s = sessionReducer(s, { type: 'speech-ended' })
    }
  }
  assert.equal(s.phase, 'listening', 'still listening after every turn')
  assert.equal(uploads, 5, 'the silent stretch is never uploaded')
  assert.equal(recorderOpenWhileSpeaking, false)
  assert.equal(s.failures, 0, 'the follow-up success reset the 429 failure')
  assert.equal(sessionReducer(s, { type: 'stop' }).phase, 'off')
})
