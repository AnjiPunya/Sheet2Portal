"""Voice assistant endpoints, layered on the text chatbot.

Same tenant/workbook authorization as ``/chat`` (``_load_workbook_for_portal``
filters by tenant, so another tenant's workbook is a 404), same history
validation (client may only send user/assistant turns), same orchestrator.

Endpoints:
  GET  /api/voice/capabilities                 what's configured (never key values)
  POST /api/workbooks/{id}/voice/transcribe    audio -> transcript (so the UI can show it early)
  POST /api/workbooks/{id}/voice/respond       history (transcript last) -> spoken-style reply
  POST /api/workbooks/{id}/voice/turn          audio + history -> transcript + reply, one round trip
  POST /api/workbooks/{id}/voice/speak         text -> server TTS audio (browser-voice fallback)
"""

import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.api.deps import get_current_tenant_id
from app.api.routes.chat import _ensure_ready, _load_chat_context
from app.api.routes.portal import _error, _load_workbook_for_portal
from app.core.config import settings
from app.core.db import get_db
from app.schemas.chat import ChatMessageIn
from app.schemas.voice import (
    LanguageModeIn,
    SpeakOut,
    SpeakRequest,
    TranscriptionOut,
    VoiceCapabilitiesOut,
    VoiceReplyOut,
    VoiceRespondRequest,
    VoiceTurnOut,
)
from app.services.ai.base import (
    ChatMessage,
    ProviderError,
    ProviderNotConfigured,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.services.ai.registry import get_provider
from app.services.ai.tools import ChatContext
from app.services.voice import stt, tts
from app.services.voice.audio import AudioValidationError, validate_audio, wav_duration_seconds
from app.services.voice.http import ProviderRejectedAudio
from app.services.voice.language import LANGUAGE_MODES, classify_transcript
from app.services.voice.service import reply_language, run_voice_reply, speech_payload, workbook_vocabulary
from app.services.voice.settings import voice_settings
from app.services.voice.speakable import to_speakable

router = APIRouter(tags=["voice"])

_HISTORY = TypeAdapter(list[ChatMessageIn])


def _provider_http_error(exc: ProviderError, what: str) -> HTTPException:
    """Map provider failures to the same status/error codes /chat uses."""
    if isinstance(exc, ProviderNotConfigured):
        return _error(503, "VOICE_NOT_CONFIGURED", str(exc))
    if isinstance(exc, ProviderRateLimited):
        err = _error(429, "PROVIDER_RATE_LIMITED", f"{what} rate limit reached ({exc.provider}). Try again shortly.")
        if exc.retry_after:
            err.headers = {"Retry-After": str(int(exc.retry_after + 0.999))}
        return err
    if isinstance(exc, ProviderTimeout):
        return _error(504, "PROVIDER_TIMEOUT", f"{what} did not respond in time.")
    if isinstance(exc, ProviderUnavailable):
        return _error(502, "PROVIDER_UNAVAILABLE", f"{what} is temporarily unavailable.")
    if isinstance(exc, ProviderRejectedAudio):
        return _error(422, "AUDIO_UNREADABLE", "The recording couldn't be decoded. Please try recording again.")
    return _error(502, "PROVIDER_ERROR", str(exc))


def _require_enabled() -> None:
    if not voice_settings.enabled:
        raise _error(503, "VOICE_DISABLED", "Voice assistant is disabled on this server.")


def _load_ctx(db: Session, workbook_id: uuid.UUID, tenant_id: uuid.UUID) -> ChatContext:
    workbook = _load_workbook_for_portal(db, workbook_id, tenant_id)
    _ensure_ready(workbook)
    ctx = _load_chat_context(db, workbook)
    if not ctx.config.entities:
        raise _error(422, "NO_USABLE_WORKSHEETS", "This workbook has no usable data for the chatbot to query.")
    return ctx


async def _read_audio(audio: UploadFile, duration_ms: int | None):
    max_seconds = voice_settings.max_audio_seconds
    # Allow a little slack for the client's own timer / encoder padding.
    if duration_ms is not None and duration_ms > (max_seconds + 2) * 1000:
        raise _error(413, "AUDIO_TOO_LONG", f"Recording is longer than {int(max_seconds)} seconds. Keep it shorter.")
    data = await audio.read(voice_settings.max_audio_bytes + 1)
    try:
        clip = validate_audio(data, voice_settings.max_audio_bytes, voice_settings.min_audio_bytes)
    except AudioValidationError as exc:
        raise _error(exc.status_code, exc.error_code, exc.message) from exc
    wav_seconds = wav_duration_seconds(data) if clip.format == "wav" else None
    if wav_seconds is not None and wav_seconds > max_seconds + 2:
        raise _error(413, "AUDIO_TOO_LONG", f"Recording is longer than {int(max_seconds)} seconds. Keep it shorter.")
    return clip


async def _transcribe(clip, mode: str, ctx: ChatContext) -> stt.Transcription:
    try:
        result = await stt.transcribe(clip, mode, workbook_vocabulary(ctx.config), settings, voice_settings)
    except ProviderError as exc:
        raise _provider_http_error(exc, "Speech recognition") from exc
    if result.silent or not result.text:
        raise _error(422, "NO_SPEECH_DETECTED", "I couldn't hear any speech. Please try again a little closer to the mic.")
    if result.duration_seconds and result.duration_seconds > voice_settings.max_audio_seconds + 2:
        raise _error(413, "AUDIO_TOO_LONG", f"Recording is longer than {int(voice_settings.max_audio_seconds)} seconds.")
    return result


async def _reply(ctx: ChatContext, messages: list[ChatMessageIn], mode: str, want_tts: bool, requested_provider: str | None, stt_language: str | None = None):
    try:
        provider = get_provider(settings, requested=requested_provider)
    except ProviderNotConfigured as exc:
        raise _error(503, "CHATBOT_NOT_CONFIGURED", str(exc)) from exc

    history = [ChatMessage(role=m.role, content=m.content) for m in messages][-settings.chat_max_history_messages :]
    language = reply_language(history, mode, stt_language)
    try:
        return await run_voice_reply(
            provider, history, ctx, language, settings, voice_settings, want_tts and tts.server_tts_available(settings, voice_settings)
        )
    except ProviderError as exc:
        raise _provider_http_error(exc, provider.name) from exc


def _parse_history(raw: str | None) -> list[ChatMessageIn]:
    if not raw:
        return []
    try:
        history = _HISTORY.validate_python(json.loads(raw))
    except (ValueError, ValidationError) as exc:
        raise _error(422, "INVALID_HISTORY", "history must be a JSON list of {role: user|assistant, content} messages") from exc
    if len(history) > 49:
        raise _error(422, "INVALID_HISTORY", "history may contain at most 49 messages")
    return history


@router.get("/api/voice/capabilities", response_model=VoiceCapabilitiesOut)
def capabilities() -> VoiceCapabilitiesOut:
    chain = stt.stt_chain(settings, voice_settings)
    return VoiceCapabilitiesOut(
        enabled=voice_settings.enabled,
        stt_available=voice_settings.enabled and bool(chain),
        stt_providers=[t.name for t in chain],
        server_tts_available=voice_settings.enabled and tts.server_tts_available(settings, voice_settings),
        max_audio_seconds=voice_settings.max_audio_seconds,
        max_audio_bytes=voice_settings.max_audio_bytes,
        language_modes=list(LANGUAGE_MODES),
    )


@router.post("/api/workbooks/{workbook_id}/voice/transcribe", response_model=TranscriptionOut)
async def transcribe(
    workbook_id: uuid.UUID,
    audio: UploadFile = File(...),
    language_mode: LanguageModeIn = Form("auto"),
    duration_ms: int | None = Form(None),
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
) -> TranscriptionOut:
    _require_enabled()
    ctx = _load_ctx(db, workbook_id, tenant_id)
    clip = await _read_audio(audio, duration_ms)
    result = await _transcribe(clip, language_mode, ctx)
    return TranscriptionOut(
        transcript=result.text,
        language="en" if language_mode == "en" else classify_transcript(result.text, result.stt_language),
        stt_language=result.stt_language,
        duration_seconds=result.duration_seconds,
        stt_provider=result.provider,
    )


@router.post("/api/workbooks/{workbook_id}/voice/respond", response_model=VoiceReplyOut)
async def respond(
    workbook_id: uuid.UUID,
    payload: VoiceRespondRequest,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
) -> VoiceReplyOut:
    _require_enabled()
    ctx = _load_ctx(db, workbook_id, tenant_id)
    if payload.messages[-1].role != "user":
        raise _error(422, "INVALID_HISTORY", "The last message must be the user's transcript.")
    reply = await _reply(ctx, payload.messages, payload.language_mode, payload.tts, payload.provider)
    return VoiceReplyOut(**reply.__dict__)


@router.post("/api/workbooks/{workbook_id}/voice/turn", response_model=VoiceTurnOut)
async def voice_turn(
    workbook_id: uuid.UUID,
    audio: UploadFile = File(...),
    language_mode: LanguageModeIn = Form("auto"),
    history: str | None = Form(None),
    tts_audio: bool = Form(False, alias="tts"),
    provider: str | None = Form(None),
    duration_ms: int | None = Form(None),
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
) -> VoiceTurnOut:
    _require_enabled()
    ctx = _load_ctx(db, workbook_id, tenant_id)
    prior = _parse_history(history)
    clip = await _read_audio(audio, duration_ms)
    result = await _transcribe(clip, language_mode, ctx)

    messages = [*prior, ChatMessageIn(role="user", content=result.text[:4000])]
    reply = await _reply(ctx, messages, language_mode, tts_audio, provider, result.stt_language)
    return VoiceTurnOut(
        **reply.__dict__,
        transcript=result.text,
        stt_language=result.stt_language,
        duration_seconds=result.duration_seconds,
        stt_provider=result.provider,
    )


@router.post("/api/workbooks/{workbook_id}/voice/speak", response_model=SpeakOut)
async def speak(
    workbook_id: uuid.UUID,
    payload: SpeakRequest,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
) -> SpeakOut:
    """Server TTS for one reply. Workbook-scoped (not a free-floating endpoint)
    so it can't be used as an open TTS proxy that burns the shared quota."""
    _require_enabled()
    _load_workbook_for_portal(db, workbook_id, tenant_id)
    text = payload.text if payload.already_speakable else to_speakable(payload.text, voice_settings.speakable_max_chars)
    if not text:
        raise _error(422, "NOTHING_TO_SPEAK", "There is no speakable text in this message.")
    try:
        audio = await speech_payload(text, settings, voice_settings)
    except ProviderError as exc:
        raise _provider_http_error(exc, "Text-to-speech") from exc
    return SpeakOut(speakable=text, audio=audio)
