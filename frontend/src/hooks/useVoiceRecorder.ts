import { useCallback, useEffect, useRef, useState } from 'react'
import {
  SilenceDetector,
  UNAVAILABLE_MESSAGES,
  micErrorMessage,
  micUnavailableReason,
  pickRecorderMimeType,
  rmsLevel,
} from '../lib/voiceAudio'

export type RecorderState = 'idle' | 'requesting' | 'recording'

export interface RecordingResult {
  blob: Blob
  durationMs: number
}

interface Options {
  maxSeconds: number
  onComplete: (result: RecordingResult) => void
  onNoSpeech: () => void
}

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
 * `autoStop: true` stops by itself after a pause in speech.
 */
export function useVoiceRecorder({ maxSeconds, onComplete, onNoSpeech }: Options) {
  const [state, setState] = useState<RecorderState>('idle')
  const [level, setLevel] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const unavailableReason = currentUnavailableReason()

  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const frameRef = useRef<number | null>(null)
  const startedAtRef = useRef(0)
  const discardRef = useRef(false)
  const detectorRef = useRef<SilenceDetector | null>(null)
  const callbacksRef = useRef({ onComplete, onNoSpeech })
  useEffect(() => {
    callbacksRef.current = { onComplete, onNoSpeech }
  }, [onComplete, onNoSpeech])

  const teardown = useCallback(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    frameRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    audioCtxRef.current?.close().catch(() => undefined)
    audioCtxRef.current = null
    recorderRef.current = null
    setLevel(0)
  }, [])

  const stop = useCallback(() => {
    const recorder = recorderRef.current
    if (recorder && recorder.state !== 'inactive') recorder.stop()
  }, [])

  const cancel = useCallback(() => {
    discardRef.current = true
    stop()
    if (!recorderRef.current) {
      teardown()
      setState('idle')
    }
  }, [stop, teardown])

  const start = useCallback(
    async ({ autoStop }: { autoStop: boolean }) => {
      if (recorderRef.current || state !== 'idle') return
      setError(null)
      if (unavailableReason) {
        setError(UNAVAILABLE_MESSAGES[unavailableReason])
        return
      }
      setState('requesting')
      let stream: MediaStream
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
        })
      } catch (err) {
        setError(micErrorMessage(err))
        setState('idle')
        return
      }
      streamRef.current = stream

      const mimeType = pickRecorderMimeType((t) => MediaRecorder.isTypeSupported(t))
      let recorder: MediaRecorder
      try {
        recorder = new MediaRecorder(stream, mimeType ? { mimeType, audioBitsPerSecond: 32000 } : undefined)
      } catch {
        setError('This browser cannot record audio in a supported format.')
        teardown()
        setState('idle')
        return
      }
      recorderRef.current = recorder
      discardRef.current = false
      const chunks: Blob[] = []
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data)
      }
      recorder.onstop = () => {
        const durationMs = performance.now() - startedAtRef.current
        const discard = discardRef.current
        // Push-to-talk (or a max-length stop) on a clip with no speech at all:
        // don't upload it -- Whisper "hears" phrases in silence and it costs quota.
        const silent = detectorRef.current !== null && !detectorRef.current.heardSpeech
        teardown()
        setState('idle')
        if (!discard && silent) {
          callbacksRef.current.onNoSpeech()
          return
        }
        if (!discard && chunks.length) {
          callbacksRef.current.onComplete({ blob: new Blob(chunks, { type: recorder.mimeType || mimeType || 'audio/webm' }), durationMs })
        }
      }

      // Level meter + voice-activity detection.
      const AudioCtx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      const detector = new SilenceDetector({ maxMs: maxSeconds * 1000 })
      detectorRef.current = null
      if (AudioCtx) {
        detectorRef.current = detector
        const ctx = new AudioCtx()
        audioCtxRef.current = ctx
        const analyser = ctx.createAnalyser()
        analyser.fftSize = 1024
        ctx.createMediaStreamSource(stream).connect(analyser)
        const buffer = new Float32Array(analyser.fftSize)
        const tick = () => {
          analyser.getFloatTimeDomainData(buffer)
          const rms = rmsLevel(buffer)
          setLevel(Math.min(1, rms * 6))
          const verdict = detector.feed(rms, performance.now())
          if (verdict === 'max-duration' || (autoStop && verdict === 'stop')) {
            stop()
            return
          }
          if (autoStop && verdict === 'no-speech') {
            stop() // onstop sees no speech and reports it
            return
          }
          frameRef.current = requestAnimationFrame(tick)
        }
        frameRef.current = requestAnimationFrame(tick)
      } else {
        // No Web Audio: still enforce the length cap.
        window.setTimeout(stop, maxSeconds * 1000)
      }

      startedAtRef.current = performance.now()
      recorder.start(250)
      setState('recording')
    },
    [maxSeconds, state, stop, teardown, unavailableReason],
  )

  useEffect(
    () => () => {
      discardRef.current = true
      const recorder = recorderRef.current
      if (recorder && recorder.state !== 'inactive') recorder.stop()
      teardown()
    },
    [teardown],
  )

  return { state, level, error, setError, start, stop, cancel, unavailableReason }
}
