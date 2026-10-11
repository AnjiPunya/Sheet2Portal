import { useCallback, useEffect, useRef, useState } from 'react'
import {
  SilenceDetector,
  UNAVAILABLE_MESSAGES,
  micErrorMessage,
  micUnavailableReason,
  pickRecorderMimeType,
  rmsLevel,
} from '../lib/voiceAudio'

/** `standby`: the mic stream is open (continuous session) but nothing is being recorded. */
export type RecorderState = 'idle' | 'requesting' | 'standby' | 'recording'

export interface RecordingResult {
  blob: Blob
  durationMs: number
}

interface Options {
  maxSeconds: number
  onComplete: (result: RecordingResult) => void
  onNoSpeech: () => void
  /** The mic went away mid-session (unplugged, permission revoked). */
  onLost?: (message: string) => void
}

interface StartOptions {
  autoStop: boolean
  /** Keep the mic stream open after this clip, for the next utterance (continuous mode). */
  keepOpen?: boolean
}

interface MicStream {
  stream: MediaStream
  ctx: AudioContext | null
  analyser: AnalyserNode | null
}

const METER_INTERVAL_MS = 50

function currentUnavailableReason() {
  if (typeof window === 'undefined') return 'no-media-devices' as const
  return micUnavailableReason({
    isSecureContext: window.isSecureContext,
    hasGetUserMedia: Boolean(navigator.mediaDevices?.getUserMedia),
    hasMediaRecorder: typeof MediaRecorder !== 'undefined',
  })
}

/**
 * MediaRecorder + Web Audio level meter with voice-activity auto-stop.
 * `start({ autoStop: false })` is push-to-talk (the caller stops it);
 * `autoStop: true` stops by itself after a pause in speech. With
 * `keepOpen: true` the mic stream survives the clip (state `standby`) so the
 * next `start` records immediately, without another permission round trip;
 * `release()` closes it.
 */
export function useVoiceRecorder({ maxSeconds, onComplete, onNoSpeech, onLost }: Options) {
  const [state, setState] = useState<RecorderState>('idle')
  const [level, setLevel] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const unavailableReason = currentUnavailableReason()

  const micRef = useRef<MicStream | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const frameRef = useRef<number | null>(null)
  const timerRef = useRef<number | null>(null)
  const startedAtRef = useRef(0)
  const discardRef = useRef(false)
  const keepOpenRef = useRef(false)
  const startingRef = useRef(false)
  const epochRef = useRef(0) // bumped by release(): a pending getUserMedia result is then dropped
  const detectorRef = useRef<SilenceDetector | null>(null)
  const callbacksRef = useRef({ onComplete, onNoSpeech, onLost })
  useEffect(() => {
    callbacksRef.current = { onComplete, onNoSpeech, onLost }
  }, [onComplete, onNoSpeech, onLost])

  const stopMeter = useCallback(() => {
    if (frameRef.current !== null) window.clearInterval(frameRef.current)
    frameRef.current = null
    if (timerRef.current !== null) window.clearTimeout(timerRef.current)
    timerRef.current = null
    setLevel(0)
  }, [])

  const closeStream = useCallback(() => {
    const mic = micRef.current
    micRef.current = null
    if (!mic) return
    mic.stream.getTracks().forEach((t) => {
      t.onended = null
      t.stop()
    })
    mic.ctx?.close().catch(() => undefined)
  }, [])

  const stop = useCallback(() => {
    const recorder = recorderRef.current
    if (recorder && recorder.state !== 'inactive') recorder.stop()
  }, [])

  /** Throw away the clip being recorded (if any). The stream stays open in continuous mode. */
  const cancel = useCallback(() => {
    discardRef.current = true
    if (recorderRef.current) return stop()
    if (!keepOpenRef.current) {
      closeStream()
      setState('idle')
    }
  }, [closeStream, stop])

  /** Discard any clip and close the mic entirely. */
  const release = useCallback(() => {
    epochRef.current += 1
    keepOpenRef.current = false
    discardRef.current = true
    const recorder = recorderRef.current
    recorderRef.current = null
    if (recorder && recorder.state !== 'inactive') recorder.stop() // onstop sees the stale recorder and does nothing
    stopMeter()
    closeStream()
    startingRef.current = false
    setState('idle')
  }, [closeStream, stopMeter])

  const openStream = useCallback(async (): Promise<MicStream | null> => {
    const existing = micRef.current
    if (existing && existing.stream.getAudioTracks().some((t) => t.readyState === 'live')) return existing
    closeStream()
    const epoch = epochRef.current
    setState('requesting')
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        // Echo cancellation also keeps the assistant's own voice out of the mic.
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      })
    } catch (err) {
      if (epoch === epochRef.current) {
        setError(micErrorMessage(err))
        setState('idle')
      }
      return null
    }
    if (epoch !== epochRef.current) {
      stream.getTracks().forEach((t) => t.stop()) // released while the permission prompt was open
      return null
    }
    let ctx: AudioContext | null = null
    let analyser: AnalyserNode | null = null
    const AudioCtx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (AudioCtx) {
      ctx = new AudioCtx()
      ctx.resume().catch(() => undefined) // Safari starts contexts created outside a gesture suspended
      analyser = ctx.createAnalyser()
      analyser.fftSize = 1024
      ctx.createMediaStreamSource(stream).connect(analyser)
    }
    const mic = { stream, ctx, analyser }
    micRef.current = mic
    stream.getAudioTracks().forEach((track) => {
      track.onended = () => {
        if (micRef.current !== mic) return
        const message = 'The microphone was disconnected or access was revoked.'
        release()
        setError(message)
        callbacksRef.current.onLost?.(message)
      }
    })
    return mic
  }, [closeStream, release])

  /** Resolves true once recording is under way, false if the mic couldn't be opened. */
  const start = useCallback(
    async ({ autoStop, keepOpen = false }: StartOptions): Promise<boolean> => {
      if (recorderRef.current || startingRef.current) return true // already recording / opening
      setError(null)
      if (unavailableReason) {
        setError(UNAVAILABLE_MESSAGES[unavailableReason])
        return false
      }
      startingRef.current = true
      const epoch = epochRef.current
      const mic = await openStream()
      startingRef.current = false
      if (!mic || epoch !== epochRef.current) return false
      keepOpenRef.current = keepOpen

      const mimeType = pickRecorderMimeType((t) => MediaRecorder.isTypeSupported(t))
      let recorder: MediaRecorder
      try {
        recorder = new MediaRecorder(mic.stream, mimeType ? { mimeType, audioBitsPerSecond: 32000 } : undefined)
      } catch {
        setError('This browser cannot record audio in a supported format.')
        closeStream()
        setState('idle')
        return false
      }
      recorderRef.current = recorder
      discardRef.current = false
      const chunks: Blob[] = []
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data)
      }
      const detector = mic.analyser ? new SilenceDetector({ maxMs: maxSeconds * 1000 }) : null
      detectorRef.current = detector
      recorder.onstop = () => {
        if (recorderRef.current !== recorder) return // released: already cleaned up
        recorderRef.current = null
        const durationMs = performance.now() - startedAtRef.current
        const discard = discardRef.current
        // A clip with no speech at all (push-to-talk, max length, or a quiet
        // stretch in continuous mode): don't upload it -- Whisper "hears"
        // phrases in silence and it costs quota.
        const silent = detector !== null && !detector.heardSpeech
        stopMeter()
        if (keepOpenRef.current) {
          setState('standby')
        } else {
          closeStream()
          setState('idle')
        }
        if (discard) return
        if (silent || !chunks.length) {
          callbacksRef.current.onNoSpeech()
          return
        }
        callbacksRef.current.onComplete({ blob: new Blob(chunks, { type: recorder.mimeType || mimeType || 'audio/webm' }), durationMs })
      }

      // Level meter + voice-activity detection.
      if (mic.analyser && detector) {
        const analyser = mic.analyser
        const buffer = new Float32Array(analyser.fftSize)
        // A timer rather than requestAnimationFrame: rAF stops in background
        // tabs, which would leave a hands-free session recording forever.
        frameRef.current = window.setInterval(() => {
          analyser.getFloatTimeDomainData(buffer)
          const rms = rmsLevel(buffer)
          setLevel(Math.min(1, rms * 6))
          const verdict = detector.feed(rms, performance.now())
          if (verdict === 'max-duration' || (autoStop && (verdict === 'stop' || verdict === 'no-speech'))) {
            stopMeter()
            stop() // onstop decides between "send" and "no speech"
          }
        }, METER_INTERVAL_MS)
      } else {
        // No Web Audio: still enforce the length cap.
        timerRef.current = window.setTimeout(stop, maxSeconds * 1000)
      }

      startedAtRef.current = performance.now()
      recorder.start(250)
      setState('recording')
      return true
    },
    [closeStream, maxSeconds, openStream, stop, stopMeter, unavailableReason],
  )

  useEffect(() => release, [release])

  return { state, level, error, setError, start, stop, cancel, release, unavailableReason }
}
