// Continuous ("hands-free") voice conversation as a pure state machine, so the
// listen -> process -> speak -> listen loop can be unit-tested with `node --test`.
//
// The mic is half-duplex: nothing is recorded while a request is in flight or
// the assistant is speaking, so its own playback can't be captured as a new
// question. Events that arrive in the wrong phase (a late reply after the user
// stopped, a stale "speech ended" after an interruption) are ignored.

export type SessionPhase = 'off' | 'listening' | 'processing' | 'speaking'

export interface SessionState {
  phase: SessionPhase
  /** Bumped every time listening (re)starts, so the recorder effect re-arms. */
  listenId: number
  /** True when listening resumes right after playback (wait for the echo tail). */
  afterSpeech: boolean
  /** Consecutive failed turns; the session ends at MAX_CONSECUTIVE_FAILURES. */
  failures: number
}

export type SessionEvent =
  | { type: 'start' }
  | { type: 'utterance' } // a clip with speech was captured and is being sent
  | { type: 'no-speech' } // nothing (usable) was said; keep listening
  | { type: 'reply'; speak: boolean }
  | { type: 'speech-ended' }
  | { type: 'interrupt' } // skip the pending request / spoken reply
  | { type: 'error'; fatal: boolean }
  | { type: 'stop' }

export const MAX_CONSECUTIVE_FAILURES = 3
/** Pause between the end of playback and re-opening the recorder. */
export const RESUME_AFTER_SPEECH_MS = 400

export const initialSession: SessionState = { phase: 'off', listenId: 0, afterSpeech: false, failures: 0 }

function listen(state: SessionState, patch: Partial<SessionState> = {}): SessionState {
  return { ...state, phase: 'listening', listenId: state.listenId + 1, afterSpeech: false, ...patch }
}

export function sessionReducer(state: SessionState, event: SessionEvent): SessionState {
  if (event.type === 'stop') return state.phase === 'off' ? state : { ...state, phase: 'off', afterSpeech: false }
  if (state.phase === 'off') {
    return event.type === 'start' ? listen(state, { failures: 0 }) : state
  }
  switch (event.type) {
    case 'start':
      return state
    case 'utterance':
      return state.phase === 'listening' ? { ...state, phase: 'processing' } : state
    case 'no-speech':
      return state.phase === 'listening' || state.phase === 'processing' ? listen(state) : state
    case 'reply':
      if (state.phase !== 'processing') return state
      return event.speak ? { ...state, phase: 'speaking', failures: 0 } : listen(state, { failures: 0 })
    case 'speech-ended':
      return state.phase === 'speaking' ? listen(state, { afterSpeech: true }) : state
    case 'interrupt':
      return state.phase === 'processing' || state.phase === 'speaking' ? listen(state) : state
    case 'error': {
      if (event.fatal) return { ...state, phase: 'off', afterSpeech: false }
      const failures = state.failures + 1
      if (failures >= MAX_CONSECUTIVE_FAILURES) return { ...state, phase: 'off', afterSpeech: false, failures }
      return listen(state, { failures })
    }
  }
}

/** Server error codes that mean "say nothing, keep listening". */
const SILENT_CODES = new Set(['NO_SPEECH_DETECTED', 'EMPTY_AUDIO'])
/** Server error codes that won't fix themselves on the next utterance. */
const FATAL_CODES = new Set([
  'VOICE_NOT_CONFIGURED',
  'VOICE_DISABLED',
  'CHATBOT_NOT_CONFIGURED',
  'PROVIDER_AUTH_FAILED',
  'PROVIDER_QUOTA_EXHAUSTED',
  'NOT_FOUND',
  'WORKBOOK_NOT_READY',
  'NO_USABLE_WORKSHEETS',
  'NOT_AUTHENTICATED', // no session cookie
  'SESSION_EXPIRED', // logged out / expired session
])

export type ErrorKind = 'silent' | 'fatal' | 'retry'

export function classifyVoiceError(errorCode: string | null): ErrorKind {
  if (errorCode && SILENT_CODES.has(errorCode)) return 'silent'
  if (errorCode && FATAL_CODES.has(errorCode)) return 'fatal'
  return 'retry' // rate limits, timeouts, provider outages, network failures
}
