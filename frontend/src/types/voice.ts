import type { ActionState } from './actions'
import type { ChatReference, ChatToolCall } from './chat'

export type DetectedLanguage = 'te' | 'en' | 'mixed'

export interface VoiceCapabilities {
  enabled: boolean
  stt_available: boolean
  stt_providers: string[]
  server_tts_available: boolean
  max_audio_seconds: number
  max_audio_bytes: number
  language_modes: string[]
}

export interface Transcription {
  transcript: string
  language: DetectedLanguage
  stt_language: string | null
  duration_seconds: number | null
  stt_provider: string
}

export interface SpeechAudio {
  mime_type: string
  base64: string
  provider: string
}

export interface VoiceReply {
  message: string
  speakable: string
  language: DetectedLanguage
  voice_lang: string
  references: ChatReference[]
  tool_calls: ChatToolCall[]
  provider: string
  audio: SpeechAudio | null
  tts_error: string | null
  action?: ActionState | null
}

export interface SpeakResponse {
  speakable: string
  audio: SpeechAudio
}
