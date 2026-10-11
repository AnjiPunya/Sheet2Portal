"""Server-side text-to-speech via Gemini TTS (free tier), used as a fallback
when the user's browser has no voice for the reply language (most desktop
browsers ship no Telugu voice).

Gemini's TTS models auto-detect the language, handle Telugu and
Telugu/English code-mixing, and return either a ready WAV (3.8 models) or
headerless 16-bit PCM (``audio/L16;rate=24000``, older previews), which is
wrapped into a WAV here so the browser can play it directly.
"""

import base64
import re
from dataclasses import dataclass

from app.core.config import Settings
from app.services.ai.base import ProviderError, ProviderNotConfigured
from app.services.voice import http
from app.services.voice.audio import pcm_to_wav
from app.services.voice.settings import VoiceSettings

GEMINI_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_RATE = re.compile(r"rate=(\d+)")


@dataclass
class SpeechAudio:
    data: bytes
    mime_type: str
    provider: str
    model: str


def server_tts_available(settings: Settings, voice: VoiceSettings) -> bool:
    return voice.server_tts_enabled and bool(settings.gemini_api_key)


async def synthesize(text: str, settings: Settings, voice: VoiceSettings) -> SpeechAudio:
    if not voice.server_tts_enabled:
        raise ProviderNotConfigured("Server text-to-speech is disabled (VOICE_SERVER_TTS_ENABLED=false).")
    if not settings.gemini_api_key:
        raise ProviderNotConfigured("Server text-to-speech needs GEMINI_API_KEY in the backend environment.")

    payload = {
        "contents": [{"parts": [{"text": text[: voice.tts_max_chars]}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice.tts_voice}}},
        },
    }
    response = await http.post(
        "Gemini TTS",
        GEMINI_GENERATE_URL.format(model=voice.tts_model),
        voice.tts_timeout_seconds,
        headers={"x-goog-api-key": settings.gemini_api_key},
        json=payload,
    )
    try:
        inline = response.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
        audio = base64.b64decode(inline["data"])
        mime = str(inline.get("mimeType") or "")
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ProviderError("Gemini TTS returned no audio") from exc

    if "wav" not in mime.lower() and audio[:4] != b"RIFF":
        match = _RATE.search(mime)
        audio = pcm_to_wav(audio, sample_rate=int(match.group(1)) if match else 24000)
    return SpeechAudio(data=audio, mime_type="audio/wav", provider="gemini", model=voice.tts_model)
