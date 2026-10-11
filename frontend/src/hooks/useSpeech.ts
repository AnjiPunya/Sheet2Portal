import { useCallback, useEffect, useRef, useState } from 'react'
import { synthesizeSpeech } from '../api/voice'
import { chunkForSpeech, pickVoice } from '../lib/voiceAudio'
import type { SpeechAudio } from '../types/voice'

// 44-byte WAV with no samples: played inside the mic-tap gesture to unlock
// audio playback on Safari/iOS, which blocks play() calls made later from
// async code (after the transcription/LLM round trips).
const SILENT_WAV = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA='

function startPlayback(el: HTMLAudioElement, url: string, onDone: () => void) {
  el.src = url
  el.onended = onDone
  el.onerror = onDone
  el.play().catch(onDone) // autoplay blocked: the text is still on screen
}

/**
 * Speaks replies. Engine order:
 *  1. audio the server already synthesized for this reply (Gemini TTS),
 *  2. the browser's own speechSynthesis voice for the language, if one exists,
 *  3. on-demand server TTS (/voice/speak) when the browser has no such voice
 *     (common for Telugu on desktop), if the server offers it.
 * `stop()` interrupts any of them immediately (used for barge-in).
 */
export function useSpeech(workbookId: string, serverTtsAvailable: boolean) {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])
  const [speaking, setSpeaking] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const urlRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const generationRef = useRef(0)
  const unlockedAudioRef = useRef<HTMLAudioElement | null>(null)
  const doneRef = useRef<(() => void) | null>(null)
  const watchdogRef = useRef<number | null>(null)
  // Chrome garbage-collects queued utterances and then never fires onend; hold them.
  const utterancesRef = useRef<SpeechSynthesisUtterance[]>([])
  const synth = typeof window !== 'undefined' && 'speechSynthesis' in window ? window.speechSynthesis : null

  useEffect(() => {
    if (!synth) return
    const load = () => setVoices(synth.getVoices())
    load()
    synth.addEventListener('voiceschanged', load)
    return () => synth.removeEventListener('voiceschanged', load)
  }, [synth])

  const hasBrowserVoice = useCallback((lang: string) => Boolean(synth && pickVoice(voices, lang)), [synth, voices])

  /** Runs the current reply's onDone exactly once (finished, failed or interrupted). */
  const settle = useCallback(() => {
    if (watchdogRef.current !== null) window.clearInterval(watchdogRef.current)
    watchdogRef.current = null
    utterancesRef.current = []
    const done = doneRef.current
    doneRef.current = null
    done?.()
  }, [])

  const stop = useCallback(() => {
    generationRef.current += 1
    abortRef.current?.abort()
    abortRef.current = null
    synth?.cancel()
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }
    if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    urlRef.current = null
    setSpeaking(false)
    settle()
  }, [settle, synth])

  /** Call synchronously from a user gesture (the mic tap) so later playback is allowed. */
  const prime = useCallback(() => {
    if (unlockedAudioRef.current) return
    try {
      synth?.speak(new SpeechSynthesisUtterance(''))
    } catch {
      /* ignore */
    }
    const el = new Audio(SILENT_WAV)
    el.play().catch(() => undefined)
    unlockedAudioRef.current = el
  }, [synth])

  const playAudio = useCallback((audio: SpeechAudio, generation: number) => {
    if (generation !== generationRef.current) return
    const bytes = Uint8Array.from(atob(audio.base64), (c) => c.charCodeAt(0))
    const url = URL.createObjectURL(new Blob([bytes], { type: audio.mime_type }))
    urlRef.current = url
    const el = unlockedAudioRef.current ?? new Audio()
    audioRef.current = el
    setSpeaking(true)
    startPlayback(el, url, () => {
      if (generation !== generationRef.current) return
      setSpeaking(false)
      settle()
    })
  }, [settle])

  /**
   * Returns false when no engine could speak this language (caller may show a
   * hint). `onDone` runs once when playback ends, fails, or is interrupted.
   */
  const speak = useCallback(
    async (text: string, lang: string, preSynthesized?: SpeechAudio | null, onDone?: () => void): Promise<boolean> => {
      stop()
      const generation = generationRef.current
      doneRef.current = onDone ?? null
      const finished = () => {
        if (generation !== generationRef.current) return
        setSpeaking(false)
        settle()
      }
      if (!text.trim()) {
        finished()
        return true
      }
      if (preSynthesized) {
        playAudio(preSynthesized, generation)
        return true
      }
      const voice = synth ? pickVoice(voices, lang) : null
      if (synth && voice) {
        const chunks = chunkForSpeech(text)
        setSpeaking(true)
        utterancesRef.current = chunks.map((chunk, i) => {
          const u = new SpeechSynthesisUtterance(chunk)
          u.voice = voice
          u.lang = voice.lang
          u.rate = 1
          if (i === chunks.length - 1) u.onend = finished
          u.onerror = finished
          synth.speak(u)
          return u
        })
        // Backstop for engines that drop onend: once the queue has drained, we're done.
        let idleTicks = 0
        watchdogRef.current = window.setInterval(() => {
          idleTicks = synth.speaking || synth.pending ? 0 : idleTicks + 1
          if (idleTicks >= 3) finished()
        }, 500)
        return true
      }
      if (serverTtsAvailable) {
        const controller = new AbortController()
        abortRef.current = controller
        setSpeaking(true)
        try {
          const res = await synthesizeSpeech(workbookId, text, controller.signal)
          playAudio(res.audio, generation)
          return true
        } catch {
          finished()
          return false
        }
      }
      finished()
      return false
    },
    [playAudio, serverTtsAvailable, settle, stop, synth, voices, workbookId],
  )

  useEffect(() => stop, [stop])

  return { speak, stop, prime, speaking, hasBrowserVoice }
}
