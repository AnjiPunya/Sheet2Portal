import { useCallback, useEffect, useReducer, useRef, useState, type PointerEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ApiRequestError } from '../api/client'
import { fetchVoiceCapabilities, sendVoiceMessage, transcribeAudio } from '../api/voice'
import { useSpeech } from '../hooks/useSpeech'
import { useVoiceRecorder, type RecordingResult } from '../hooks/useVoiceRecorder'
import { LANGUAGE_MODE_OPTIONS, UNAVAILABLE_MESSAGES, type LanguageMode } from '../lib/voiceAudio'
import {
  MAX_CONSECUTIVE_FAILURES,
  RESUME_AFTER_SPEECH_MS,
  classifyVoiceError,
  initialSession,
  sessionReducer,
  type SessionPhase,
} from '../lib/voiceSession'
import type { ActionContext } from '../api/chat'
import type { ActionState } from '../types/actions'
import type { ChatMessage } from '../types/chat'
import type { VoiceReply } from '../types/voice'

const MODE_KEY = 'sheet2portal.voice.languageMode'
const MUTE_KEY = 'sheet2portal.voice.muted'
const HOLD_MS = 350

function readStored<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const v = localStorage.getItem(key)
    return v && (allowed as readonly string[]).includes(v) ? (v as T) : fallback
  } catch {
    return fallback
  }
}

function store(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* private mode etc. -- preference just isn't remembered */
  }
}

type Work = 'idle' | 'transcribing' | 'thinking'

const STATUS_TEXT = {
  requesting: 'Waiting for microphone permission…',
  listening: 'Listening… tap to finish, or just pause',
  sessionListening: 'Listening… ask your question, then pause',
  holding: 'Listening… release to send',
  transcribing: 'Transcribing…',
  thinking: 'Thinking…',
  speaking: 'Speaking…',
}

const SESSION_BADGE: Record<Exclude<SessionPhase, 'off'>, { label: string; className: string }> = {
  listening: { label: 'Listening', className: 'bg-emerald-50 text-emerald-700' },
  processing: { label: 'Processing', className: 'bg-amber-50 text-amber-700' },
  speaking: { label: 'Speaking', className: 'bg-indigo-50 text-indigo-700' },
}

/**
 * Mic bar for the chat widget. Tap = hands-free conversation: it keeps
 * listening, sends each question when you pause, speaks the reply, then
 * listens again until you tap the mic again (or press Esc). Press-and-hold =
 * one push-to-talk question. Transcripts and replies are handed to the parent
 * so they land in the same chat history as typed messages.
 */
export function VoiceAssistant({
  workbookId,
  history,
  disabled,
  actionContext,
  onTranscript,
  onReply,
  onAction,
}: {
  workbookId: string
  history: ChatMessage[]
  disabled?: boolean
  /** Same draft -> confirm flow as typed chat: a spoken "yes" confirms the draft on screen. */
  actionContext?: ActionContext
  onTranscript: (text: string) => void
  onReply: (reply: VoiceReply) => void
  onAction?: (action: ActionState) => void
}) {
  const capsQuery = useQuery({ queryKey: ['voice-capabilities'], queryFn: fetchVoiceCapabilities, staleTime: Infinity, retry: false })
  const caps = capsQuery.data
  const [mode, setMode] = useState<LanguageMode>(() => readStored(MODE_KEY, ['auto', 'te', 'en'] as const, 'auto'))
  const [muted, setMuted] = useState(() => readStored(MUTE_KEY, ['true', 'false'] as const, 'false') === 'true')
  const [work, setWork] = useState<Work>('idle')
  const [notice, setNotice] = useState<string | null>(null)
  const [holding, setHolding] = useState(false)
  const [session, dispatch] = useReducer(sessionReducer, initialSession)

  const serverTts = Boolean(caps?.server_tts_available)
  const speech = useSpeech(workbookId, serverTts)
  const historyRef = useRef(history)
  const actionContextRef = useRef(actionContext)
  useEffect(() => {
    historyRef.current = history
    actionContextRef.current = actionContext
  }, [history, actionContext])
  // Read inside long-running async turns, so they see the latest values.
  const sessionRef = useRef(session)
  const mutedRef = useRef(muted)
  useEffect(() => {
    sessionRef.current = session
    mutedRef.current = muted
  }, [session, muted])
  const abortRef = useRef<AbortController | null>(null)
  const holdTimerRef = useRef<number | null>(null)
  const pttRef = useRef(false)
  const suppressClickRef = useRef(false)

  const handleRecording = useCallback(
    async ({ blob, durationMs }: RecordingResult) => {
      const inSession = sessionRef.current.phase !== 'off'
      if (inSession) dispatch({ type: 'utterance' })
      const controller = new AbortController()
      abortRef.current = controller
      setNotice(null)
      try {
        setWork('transcribing')
        const t = await transcribeAudio(workbookId, blob, mode, durationMs, controller.signal)
        onTranscript(t.transcript)

        const voiceLang = t.language === 'en' ? 'en-IN' : 'te-IN'
        // Ask the server to synthesize up front only when this device has no
        // voice for the language -- saves a round trip and the TTS quota.
        const wantServerTts = !mutedRef.current && serverTts && !speech.hasBrowserVoice(voiceLang)
        setWork('thinking')
        const messages: ChatMessage[] = [
          ...historyRef.current.map(({ role, content }) => ({ role, content })),
          { role: 'user', content: t.transcript },
        ]
        const reply = await sendVoiceMessage(workbookId, messages.slice(-50), mode, wantServerTts, controller.signal, actionContextRef.current)
        if (controller.signal.aborted) return
        onReply(reply)
        if (reply.action) onAction?.(reply.action)
        setWork('idle')

        const speak = !mutedRef.current
        if (inSession) dispatch({ type: 'reply', speak })
        if (speak) {
          // In a session, listening resumes when playback ends (or is interrupted).
          const spoke = await speech.speak(reply.speakable, reply.voice_lang, reply.audio, () => dispatch({ type: 'speech-ended' }))
          if (!spoke) {
            setNotice(
              reply.voice_lang.startsWith('te')
                ? 'No Telugu voice is available on this device, so the reply is shown as text only.'
                : 'Speech playback is not available in this browser.',
            )
          }
        }
      } catch (err) {
        if (controller.signal.aborted) return
        const code = err instanceof ApiRequestError ? err.errorCode : null
        const kind = classifyVoiceError(code)
        if (inSession && kind === 'silent') {
          dispatch({ type: 'no-speech' }) // Whisper heard nothing usable: just keep listening
          return
        }
        const message = err instanceof ApiRequestError ? err.message : 'Voice request failed. Check your connection and try again.'
        if (inSession) {
          const willStop = kind === 'fatal' || sessionRef.current.failures + 1 >= MAX_CONSECUTIVE_FAILURES
          setNotice(willStop ? `${message} Voice conversation stopped.` : `${message} Still listening…`)
          dispatch({ type: 'error', fatal: kind === 'fatal' })
        } else {
          setNotice(message)
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null
        setWork('idle')
      }
    },
    [mode, onAction, onReply, onTranscript, serverTts, speech, workbookId],
  )

  const handleNoSpeech = useCallback(() => {
    if (sessionRef.current.phase !== 'off') {
      dispatch({ type: 'no-speech' }) // a quiet stretch in a conversation: keep listening
      return
    }
    setNotice("I didn't hear anything. Tap the mic and speak, or hold it while you talk.")
  }, [])

  const handleMicLost = useCallback(() => dispatch({ type: 'error', fatal: true }), [])

  const recorder = useVoiceRecorder({
    maxSeconds: caps?.max_audio_seconds ?? 60,
    onComplete: handleRecording,
    onNoSpeech: handleNoSpeech,
    onLost: handleMicLost,
  })
  const { start: startRecorder, release: releaseRecorder } = recorder
  const { stop: stopSpeech } = speech

  // Session loop: (re)open the recorder whenever the session enters listening.
  useEffect(() => {
    if (session.phase !== 'listening') return
    const listenId = session.listenId
    const timer = window.setTimeout(
      () => {
        void startRecorder({ autoStop: true, keepOpen: true }).then((ok) => {
          const current = sessionRef.current
          if (!ok && current.phase === 'listening' && current.listenId === listenId) dispatch({ type: 'error', fatal: true })
        })
      },
      // Let the tail of the spoken reply die away so it isn't recorded as a question.
      session.afterSpeech ? RESUME_AFTER_SPEECH_MS : 0,
    )
    return () => window.clearTimeout(timer)
  }, [session.phase, session.listenId, session.afterSpeech, startRecorder])

  // Session ended (stop, fatal error, too many failures): free the mic and go quiet.
  useEffect(() => {
    if (session.phase !== 'off') return
    abortRef.current?.abort()
    releaseRecorder()
    stopSpeech()
  }, [session.phase, releaseRecorder, stopSpeech])

  useEffect(() => () => abortRef.current?.abort(), [])

  const inSession = session.phase !== 'off'
  const busy = work !== 'idle'
  const recording = recorder.state === 'recording'
  const unavailable = !caps?.enabled || !caps?.stt_available || Boolean(recorder.unavailableReason)
  const micDisabled = !inSession && (disabled || capsQuery.isLoading || (unavailable && !recording))

  function beginListening(autoStop: boolean) {
    speech.stop() // barge-in: talking over the assistant stops it
    speech.prime() // inside the tap gesture, so later replies may play (Safari/iOS)
    setNotice(null)
    recorder.setError(null)
    void recorder.start({ autoStop })
  }

  function startSession() {
    speech.stop()
    speech.prime()
    setNotice(null)
    recorder.setError(null)
    dispatch({ type: 'start' })
  }

  function endSession() {
    dispatch({ type: 'stop' })
  }

  /** Skip the pending request or the reply being spoken; keep the conversation going. */
  function interrupt() {
    abortRef.current?.abort()
    setWork('idle')
    dispatch({ type: 'interrupt' })
    speech.stop()
  }

  function onPointerDown(e: PointerEvent) {
    if (e.button !== 0 || inSession || busy || recording || micDisabled) return
    holdTimerRef.current = window.setTimeout(() => {
      pttRef.current = true
      setHolding(true)
      beginListening(false)
    }, HOLD_MS)
  }

  function endHold() {
    if (holdTimerRef.current !== null) window.clearTimeout(holdTimerRef.current)
    holdTimerRef.current = null
    if (pttRef.current) {
      pttRef.current = false
      suppressClickRef.current = true
      setHolding(false)
      recorder.stop()
    }
  }

  function onClick() {
    if (suppressClickRef.current) {
      suppressClickRef.current = false
      return
    }
    if (inSession) return endSession()
    if (recording) return recorder.stop()
    if (busy) {
      abortRef.current?.abort()
      setWork('idle')
      return
    }
    startSession()
  }

  function toggleMute() {
    const next = !muted
    setMuted(next)
    store(MUTE_KEY, String(next))
    if (next) speech.stop() // in a session this resumes listening
  }

  const status =
    recorder.state === 'requesting'
      ? STATUS_TEXT.requesting
      : recording
        ? holding
          ? STATUS_TEXT.holding
          : inSession
            ? STATUS_TEXT.sessionListening
            : STATUS_TEXT.listening
        : work !== 'idle'
          ? STATUS_TEXT[work]
          : speech.speaking
            ? STATUS_TEXT.speaking
            : inSession && session.phase === 'listening'
              ? STATUS_TEXT.sessionListening
              : null

  const unavailableText = recorder.unavailableReason
    ? UNAVAILABLE_MESSAGES[recorder.unavailableReason]
    : capsQuery.isError
      ? 'Voice input is unavailable right now.'
      : caps && (!caps.enabled || !caps.stt_available)
        ? 'Voice input is not configured on the server.'
        : null
  const message = recorder.error ?? notice ?? unavailableText

  const micLabel = inSession
    ? 'Stop voice conversation'
    : recording
      ? 'Stop recording and send'
      : busy
        ? 'Cancel voice request'
        : 'Start a voice conversation (tap), or press and hold to ask one question'
  const canInterrupt = inSession ? session.phase === 'processing' || session.phase === 'speaking' : speech.speaking
  const badge = inSession ? SESSION_BADGE[session.phase as Exclude<SessionPhase, 'off'>] : null

  return (
    <div className="border-t border-slate-100 px-3 py-2">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onClick}
          onPointerDown={onPointerDown}
          onPointerUp={endHold}
          onPointerLeave={endHold}
          onPointerCancel={endHold}
          onContextMenu={(e) => e.preventDefault()}
          onKeyDown={(e) => {
            if (e.key !== 'Escape') return
            if (inSession) endSession()
            else if (recording) recorder.cancel()
          }}
          disabled={micDisabled && !busy}
          aria-label={micLabel}
          aria-pressed={inSession || recording}
          title={recorder.unavailableReason ? 'Voice input unavailable' : micLabel}
          className={`relative flex h-9 w-9 shrink-0 touch-none select-none items-center justify-center rounded-full text-white transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-40 ${
            inSession || recording ? 'bg-red-500 hover:bg-red-600' : busy ? 'bg-slate-400' : 'bg-indigo-600 hover:bg-indigo-700'
          }`}
        >
          {recording && (
            <span
              aria-hidden
              className="absolute inset-0 rounded-full bg-red-400 opacity-60"
              style={{ transform: `scale(${1 + recorder.level * 0.6})`, transition: 'transform 80ms linear' }}
            />
          )}
          {busy && !inSession ? (
            <svg aria-hidden className="relative h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" strokeOpacity="0.3" />
              <path d="M21 12a9 9 0 00-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            </svg>
          ) : inSession || recording ? (
            <svg aria-hidden className="relative h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <rect x="5" y="5" width="10" height="10" rx="2" />
            </svg>
          ) : (
            <svg aria-hidden className="relative h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path d="M10 2a3 3 0 00-3 3v5a3 3 0 006 0V5a3 3 0 00-3-3z" />
              <path d="M5 9a1 1 0 00-2 0 7 7 0 006 6.93V18H7a1 1 0 100 2h6a1 1 0 100-2h-2v-2.07A7 7 0 0017 9a1 1 0 10-2 0 5 5 0 01-10 0z" />
            </svg>
          )}
        </button>

        <div className="flex min-w-0 flex-1 items-center gap-2" aria-live="polite">
          {badge && (
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${badge.className}`}>{badge.label}</span>
          )}
          {recording ? (
            <div className="flex items-center gap-2">
              <div aria-hidden className="flex h-4 items-end gap-0.5">
                {[0.15, 0.35, 0.55, 0.75, 0.95].map((step) => (
                  <span
                    key={step}
                    className={`w-1 rounded-sm ${recorder.level >= step * 0.6 ? 'bg-red-500' : 'bg-slate-200'}`}
                    style={{ height: `${30 + step * 70}%` }}
                  />
                ))}
              </div>
              <span className="truncate text-xs text-slate-500">{status}</span>
            </div>
          ) : (
            <span className="block truncate text-xs text-slate-400">{status ?? 'Tap the mic for a voice conversation'}</span>
          )}
        </div>

        <label className="sr-only" htmlFor={`voice-lang-${workbookId}`}>
          Speech language
        </label>
        <select
          id={`voice-lang-${workbookId}`}
          value={mode}
          onChange={(e) => {
            const next = e.target.value as LanguageMode
            setMode(next)
            store(MODE_KEY, next)
          }}
          disabled={busy || (!inSession && recording)}
          title="Speech language"
          className="rounded-md border border-slate-200 bg-white px-1.5 py-1 text-xs text-slate-600 focus:border-indigo-400 focus:outline-none"
        >
          {LANGUAGE_MODE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value} title={o.hint}>
              {o.label}
            </option>
          ))}
        </select>

        <button
          type="button"
          onClick={toggleMute}
          aria-pressed={muted}
          aria-label={muted ? 'Unmute spoken replies' : 'Mute spoken replies'}
          title={muted ? 'Spoken replies off' : 'Spoken replies on'}
          className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
        >
          <svg aria-hidden className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path d="M9.383 3.076A1 1 0 0110 4v12a1 1 0 01-1.707.707L4.586 13H2a1 1 0 01-1-1V8a1 1 0 011-1h2.586l3.707-3.707a1 1 0 011.09-.217z" />
            {muted ? (
              <path d="M13.293 7.293a1 1 0 011.414 0L16 8.586l1.293-1.293a1 1 0 111.414 1.414L17.414 10l1.293 1.293a1 1 0 01-1.414 1.414L16 11.414l-1.293 1.293a1 1 0 01-1.414-1.414L14.586 10l-1.293-1.293a1 1 0 010-1.414z" />
            ) : (
              <path d="M14.657 5.757a1 1 0 011.414 0A6 6 0 0118 10a6 6 0 01-1.929 4.243 1 1 0 11-1.414-1.414A4 4 0 0016 10a4 4 0 00-1.343-2.829 1 1 0 010-1.414z" />
            )}
          </svg>
        </button>

        {canInterrupt && (
          <button
            type="button"
            onClick={inSession ? interrupt : speech.stop}
            title={inSession ? 'Skip this reply and keep listening' : 'Stop speaking'}
            className="rounded-md px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            {inSession ? 'Interrupt' : 'Stop'}
          </button>
        )}
      </div>
      {message && (
        <p role="status" className="mt-1.5 text-xs text-amber-700">
          {message}
        </p>
      )}
    </div>
  )
}
