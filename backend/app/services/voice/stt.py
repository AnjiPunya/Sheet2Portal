"""Speech-to-text: Groq Whisper (primary) with Gemini audio understanding as fallback.

Findings from live testing that shape this module:

* ``whisper-large-v3`` with *no* language and *no* prompt translated
  code-mixed Telugu/English speech into English. A short code-mixed
  ``prompt`` fixes that (Telugu words stay in Telugu script, English words
  in Latin), so Auto mode always sends one.
* Forcing ``language=te`` transliterates English words into Telugu script
  ("టోటల బజెట"), which is why Auto -- not Telugu -- is the default mode.
* ``whisper-large-v3-turbo`` misdetected the same clip as Gujarati, so Auto
  mode retries once with ``language=te`` when Whisper reports a language
  other than Telugu/English (Indian users of this app speak one of the two).
"""

import base64
import json
import re
from dataclasses import dataclass

from app.core.config import Settings
from app.services.ai.base import ProviderError, ProviderNotConfigured, ProviderRateLimited, ProviderUnavailable
from app.services.voice import http
from app.services.voice.audio import AudioClip
from app.services.voice.language import LanguageMode, fold_indic_into_telugu, normalize_stt_language
from app.services.voice.settings import VoiceSettings

GROQ_TRANSCRIPTIONS_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GEMINI_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Whisper's prompt is capped at 224 tokens; Telugu script is token-hungry.
_MAX_PROMPT_CHARS = 380
_BASE_PROMPT = (
    "Telugu and English mixed conversation about spreadsheet data. English words stay in English: "
    "total budget ఎంత? pending tasks ఎన్ని ఉన్నాయి? overdue items చూపించు."
)
_EN_PROMPT = "A question about spreadsheet data, like total budget, pending tasks or overdue items."

# Whisper famously "hears" these on silent or near-silent clips. The first
# set is never a plausible question to a data assistant, so it always counts
# as silence (live: "Subtitles by the Amara.org community" came back for
# pure silence with a low no_speech_prob). The second set could be real
# speech, so it only counts when Whisper itself suspects silence.
_ALWAYS_HALLUCINATIONS = {
    "thanks for watching", "thank you for watching", "subtitles by the amaraorg community",
    "please subscribe", "like and subscribe",
}
_HALLUCINATION_MARKERS = ("amaraorg", "subtitles by", "transcribed by")
_HALLUCINATIONS = {"thank you", "you", "bye", "okay", "ధన్యవాదాలు"}
_NO_SPEECH_THRESHOLD = 0.6


@dataclass
class Transcription:
    text: str
    stt_language: str | None  # ISO code reported by the STT ("te"/"en") or None if unknown/other
    duration_seconds: float | None
    provider: str
    model: str
    silent: bool = False


def build_prompt(mode: LanguageMode, vocabulary: list[str]) -> str:
    """Whisper prompt: the workbook's own sheet/field names (so domain words
    are spelled right), then the language-style example LAST.

    Whisper treats the prompt as the preceding transcript and continues in
    its style. Live testing: ending the prompt with the English field list
    made Whisper *translate* a Telugu follow-up into English ("How many delays
    are there?"); putting the vocabulary first and ending on the code-mixed
    example kept it in Telugu script ("మరి వాటిలో ఎన్ని delayed ఉన్నాయి?").
    """
    base = _EN_PROMPT if mode == "en" else _BASE_PROMPT
    budget = _MAX_PROMPT_CHARS - len(base) - 2
    terms: list[str] = []
    for word in vocabulary:
        if len(", ".join([*terms, word])) > budget:
            break
        terms.append(word)
    return f"{', '.join(terms)}. {base}" if terms else base


def _normalise(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower(), flags=re.UNICODE).strip()


def looks_silent(text: str, segments: list[dict], prompt: str) -> bool:
    norm = _normalise(text)
    if not norm:
        return True
    if segments and all((s.get("no_speech_prob") or 0) >= _NO_SPEECH_THRESHOLD for s in segments):
        return True
    max_no_speech = max(((s.get("no_speech_prob") or 0) for s in segments), default=0)
    if norm in _ALWAYS_HALLUCINATIONS or any(m in norm for m in _HALLUCINATION_MARKERS):
        return True
    if norm in _HALLUCINATIONS and max_no_speech >= 0.2:
        return True
    # On silence Whisper sometimes just echoes its prompt back. Only long
    # echoes count -- the prompt's short example questions are real ones.
    if len(norm) >= 40 and norm in _normalise(prompt):
        return True
    return False


class GroqWhisperTranscriber:
    name = "groq"

    def __init__(self, api_key: str, model: str, timeout: float):
        self._api_key = api_key
        self.model = model
        self._timeout = timeout

    async def _request(self, clip: AudioClip, language: str | None, prompt: str) -> dict:
        data = {"model": self.model, "response_format": "verbose_json", "temperature": "0", "prompt": prompt}
        if language:
            data["language"] = language
        response = await http.post(
            "Groq Whisper",
            GROQ_TRANSCRIPTIONS_URL,
            self._timeout,
            audio_request=True,
            headers={"Authorization": f"Bearer {self._api_key}"},
            data=data,
            files={"file": (f"speech.{clip.format}", clip.data, clip.mime_type)},
        )
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError("Groq Whisper returned an unreadable response") from exc

    async def transcribe(self, clip: AudioClip, mode: LanguageMode, vocabulary: list[str]) -> Transcription:
        prompt = build_prompt(mode, vocabulary)
        body = await self._request(clip, None if mode == "auto" else mode, prompt)
        reported = body.get("language")
        if mode == "auto" and reported and normalize_stt_language(reported) is None and (body.get("text") or "").strip():
            body = await self._request(clip, "te", prompt)
            reported = body.get("language")

        text = fold_indic_into_telugu((body.get("text") or "").strip())
        segments = body.get("segments") or []
        return Transcription(
            text=text,
            stt_language=normalize_stt_language(reported) or (None if mode == "auto" else mode),
            duration_seconds=body.get("duration"),
            provider=self.name,
            model=self.model,
            silent=looks_silent(text, segments, prompt),
        )


_GEMINI_STT_INSTRUCTION = (
    "Transcribe this voice clip verbatim. The speaker uses Telugu, English, or a mix of both. "
    "Write Telugu words in Telugu script and English words in English (Latin script); do not translate. "
    "Respond only with JSON: {{\"text\": <transcript>, \"language\": \"te\" | \"en\" | \"mixed\" | \"none\"}}. "
    "Use \"none\" with an empty text if there is no speech.{hint}"
)


class GeminiTranscriber:
    """Fallback STT via Gemini's audio understanding (free tier on Flash)."""

    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float):
        self._api_key = api_key
        self.model = model
        self._timeout = timeout

    async def transcribe(self, clip: AudioClip, mode: LanguageMode, vocabulary: list[str]) -> Transcription:
        hint = {"te": " The speaker is using Telugu.", "en": " The speaker is using English."}.get(mode, "")
        if vocabulary:
            hint += " Words that may appear: " + ", ".join(vocabulary[:30]) + "."
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": _GEMINI_STT_INSTRUCTION.format(hint=hint)},
                        {"inline_data": {"mime_type": clip.mime_type, "data": base64.b64encode(clip.data).decode()}},
                    ]
                }
            ],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        response = await http.post(
            "Gemini",
            GEMINI_GENERATE_URL.format(model=self.model),
            self._timeout,
            audio_request=True,
            headers={"x-goog-api-key": self._api_key},
            json=payload,
        )
        try:
            parts = response.json()["candidates"][0]["content"]["parts"]
            raw = "".join(p.get("text", "") for p in parts)
            parsed = json.loads(raw)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Gemini returned an unreadable transcription") from exc

        text = fold_indic_into_telugu(str(parsed.get("text") or "").strip())
        language = str(parsed.get("language") or "")
        return Transcription(
            text=text,
            stt_language=normalize_stt_language(language),
            duration_seconds=None,
            provider=self.name,
            model=self.model,
            silent=language == "none" or not _normalise(text),
        )


def _build(name: str, settings: Settings, voice: VoiceSettings):
    if name == "groq" and settings.groq_api_key:
        return GroqWhisperTranscriber(settings.groq_api_key, voice.stt_model, voice.stt_timeout_seconds)
    if name == "gemini" and settings.gemini_api_key:
        return GeminiTranscriber(settings.gemini_api_key, voice.gemini_stt_model, voice.stt_timeout_seconds)
    return None


def stt_chain(settings: Settings, voice: VoiceSettings) -> list:
    """Configured transcribers, preferred first."""
    preferred = (voice.stt_provider or "groq").lower()
    order = [preferred] + [n for n in ("groq", "gemini") if n != preferred]
    return [t for t in (_build(n, settings, voice) for n in order) if t is not None]


async def transcribe(
    clip: AudioClip, mode: LanguageMode, vocabulary: list[str], settings: Settings, voice: VoiceSettings
) -> Transcription:
    """Transcribe with the preferred provider, falling back to the next one on
    rate limits/outages (free tiers run out). Audio rejections aren't retried
    elsewhere -- a bad file is bad for every provider."""
    chain = stt_chain(settings, voice)
    if not chain:
        raise ProviderNotConfigured(
            "Voice input is not configured. Set GROQ_API_KEY (Whisper) or GEMINI_API_KEY in the backend environment."
        )
    last_exc: ProviderError | None = None
    for transcriber in chain:
        try:
            return await transcriber.transcribe(clip, mode, vocabulary)
        except (ProviderRateLimited, ProviderUnavailable) as exc:
            last_exc = exc
    assert last_exc is not None
    raise last_exc
