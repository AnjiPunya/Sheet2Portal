"""Voice-only settings, read from the same ``.env`` with a ``VOICE_`` prefix.

API keys are NOT duplicated here -- the voice pipeline reuses the chatbot's
GROQ_API_KEY / GEMINI_API_KEY from ``app.core.config.settings``. Every knob
below has a working default, so no new environment variable is required.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class VoiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="VOICE_", extra="ignore")

    enabled: bool = True

    # Speech-to-text. whisper-large-v3 (not -turbo): in testing, turbo
    # misdetected Telugu/English code-mixed speech as Gujarati.
    stt_provider: str = "groq"  # "groq" (Whisper) or "gemini" (audio-understanding fallback)
    stt_model: str = "whisper-large-v3"
    gemini_stt_model: str = "gemini-flash-latest"
    # Gemini free-tier quotas are per model and small (live: 20 requests/day
    # on the Flash model), so the STT fallback tries these next on 429/5xx/404.
    gemini_stt_fallback_models: str = "gemini-flash-lite-latest"
    stt_timeout_seconds: float = 30.0

    # Upload limits. Opus from MediaRecorder is ~16-32 kbps, so 60s is well
    # under 1 MB; the byte cap is a generous backstop for wav/m4a uploads.
    max_audio_bytes: int = 3 * 1024 * 1024
    max_audio_seconds: float = 60.0
    min_audio_bytes: int = 512

    # Text-to-speech. The browser's speechSynthesis is the primary engine
    # (free, instant); the server-side Gemini TTS is the fallback for
    # devices without a Telugu voice. Its free-tier daily quota is small, so
    # it can be switched off with VOICE_SERVER_TTS_ENABLED=false.
    server_tts_enabled: bool = True
    tts_model: str = "gemini-3.8-flash-lite-tts"
    # Tried in order when the primary model is rate limited (3 RPM per model
    # on the free tier, measured live), unavailable or retired.
    tts_fallback_models: str = "gemini-3.8-flash-tts,gemini-2.5-flash-preview-tts"
    tts_voice: str = "Kore"
    tts_timeout_seconds: float = 30.0
    tts_max_chars: int = 600

    # Spoken replies are trimmed to this many characters (at a sentence
    # boundary) -- the full text still appears in the chat bubble.
    speakable_max_chars: int = 600


voice_settings = VoiceSettings()
