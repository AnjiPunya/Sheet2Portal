import { apiFetch, throwApiError } from './client'
import { actionBody, type ActionContext } from './chat'
import type { ChatMessage } from '../types/chat'
import type { SpeakResponse, Transcription, VoiceCapabilities, VoiceReply } from '../types/voice'
import { fileExtensionFor, type LanguageMode } from '../lib/voiceAudio'

export async function fetchVoiceCapabilities(): Promise<VoiceCapabilities> {
  const res = await apiFetch(`/api/voice/capabilities`)
  if (!res.ok) return throwApiError(res)
  return res.json()
}

export async function transcribeAudio(
  workbookId: string,
  audio: Blob,
  languageMode: LanguageMode,
  durationMs: number,
  signal?: AbortSignal,
): Promise<Transcription> {
  const form = new FormData()
  form.append('audio', audio, `speech.${fileExtensionFor(audio.type)}`)
  form.append('language_mode', languageMode)
  form.append('duration_ms', String(Math.round(durationMs)))
  const res = await apiFetch(`/api/workbooks/${workbookId}/voice/transcribe`, { method: 'POST', body: form, signal })
  if (!res.ok) return throwApiError(res)
  return res.json()
}

export async function sendVoiceMessage(
  workbookId: string,
  messages: ChatMessage[],
  languageMode: LanguageMode,
  tts: boolean,
  signal?: AbortSignal,
  context?: ActionContext,
): Promise<VoiceReply> {
  const res = await apiFetch(`/api/workbooks/${workbookId}/voice/respond`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, language_mode: languageMode, tts, ...actionBody(context) }),
    signal,
  })
  if (!res.ok) return throwApiError(res)
  return res.json()
}

export async function synthesizeSpeech(workbookId: string, text: string, signal?: AbortSignal): Promise<SpeakResponse> {
  const res = await apiFetch(`/api/workbooks/${workbookId}/voice/speak`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, already_speakable: true }),
    signal,
  })
  if (!res.ok) return throwApiError(res)
  return res.json()
}
