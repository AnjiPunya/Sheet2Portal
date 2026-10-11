"""The voice turn pipeline: transcript -> existing chat orchestrator (in the
user's language) -> speakable text -> optional server TTS."""

import base64
from dataclasses import dataclass

from app.core.config import Settings
from app.services.ai.base import ChatMessage, LLMProvider, ProviderError
from app.services.ai.orchestrator import extract_references, run_chat_turn
from app.services.ai.tools import ChatContext
from app.services.analysis.types import PortalConfig
from app.services.voice import tts
from app.services.voice.language import DetectedLanguage, browser_voice_lang, classify_transcript, reply_instruction
from app.services.voice.settings import VoiceSettings
from app.services.voice.speakable import to_speakable
from app.services.voice.style import VoiceStyleProvider

FALLBACK_REPLY = {
    "te": "క్షమించండి, సమాధానం ఇవ్వలేకపోయాను. దయచేసి మళ్ళీ అడగండి.",
    "mixed": "Sorry, సమాధానం ఇవ్వలేకపోయాను. దయచేసి మళ్ళీ అడగండి.",
    "en": "I wasn't able to generate a response. Please try rephrasing your question.",
}


@dataclass
class VoiceReply:
    message: str
    speakable: str
    language: DetectedLanguage
    voice_lang: str
    references: list[dict]
    tool_calls: list[dict]
    provider: str
    audio: dict | None = None
    tts_error: str | None = None


def workbook_vocabulary(config: PortalConfig, limit: int = 40) -> list[str]:
    """Worksheet and field names, used to bias transcription toward the workbook's own terms."""
    words: list[str] = []
    seen: set[str] = set()
    for entity in config.entities:
        for name in [entity.worksheet, *(c.name for c in entity.columns)]:
            name = str(name).strip()[:40]
            if name and name.lower() not in seen:
                seen.add(name.lower())
                words.append(name)
            if len(words) >= limit:
                return words
    return words


def reply_language(history: list[ChatMessage], mode: str, stt_language: str | None = None) -> DetectedLanguage:
    if mode == "en":
        return "en"
    last_user = next((m.content or "" for m in reversed(history) if m.role == "user"), "")
    detected = classify_transcript(last_user, stt_language)
    if mode == "te" and detected == "en":
        # User explicitly chose Telugu; an all-English transcript under that
        # mode is usually code-mixed speech, so answer in the mixed style.
        return "mixed"
    return detected


async def speech_payload(text: str, settings: Settings, voice: VoiceSettings) -> dict:
    audio = await tts.synthesize(text, settings, voice)
    return {"mime_type": audio.mime_type, "base64": base64.b64encode(audio.data).decode(), "provider": audio.provider}


async def run_voice_reply(
    provider: LLMProvider,
    history: list[ChatMessage],
    ctx: ChatContext,
    language: DetectedLanguage,
    settings: Settings,
    voice: VoiceSettings,
    want_tts: bool,
) -> VoiceReply:
    """Run one chat turn through the *unchanged* orchestrator, styled for voice.

    Provider errors propagate (the route maps them to HTTP codes). TTS errors
    don't: the text answer is still useful, so they're reported in
    ``tts_error`` and the client can fall back to browser speech.
    """
    styled = VoiceStyleProvider(provider, reply_instruction(language))
    result, tool_log = await run_chat_turn(
        styled,
        history,
        ctx,
        max_iterations=settings.chat_max_tool_iterations,
        max_page_size=settings.chat_tool_max_page_size,
    )
    message = (result.message.content or "").strip() or FALLBACK_REPLY[language]
    speakable = to_speakable(message, voice.speakable_max_chars) or FALLBACK_REPLY[language]

    reply = VoiceReply(
        message=message,
        speakable=speakable,
        language=language,
        voice_lang=browser_voice_lang(language),
        references=extract_references(tool_log),
        tool_calls=[{"name": e["name"], "arguments": e["arguments"]} for e in tool_log],
        provider=provider.name,
    )
    if want_tts:
        try:
            reply.audio = await speech_payload(speakable, settings, voice)
        except ProviderError as exc:
            reply.tts_error = str(exc)
    return reply
