from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.actions import ActionStateOut, ConversationId, PendingActionIn
from app.schemas.chat import ChatMessageIn, ChatReferenceOut, ChatToolCallOut

LanguageModeIn = Literal["auto", "te", "en"]
DetectedLanguageOut = Literal["te", "en", "mixed"]


class VoiceCapabilitiesOut(BaseModel):
    enabled: bool
    stt_available: bool
    stt_providers: list[str]
    server_tts_available: bool
    max_audio_seconds: float
    max_audio_bytes: int
    language_modes: list[str]


class TranscriptionOut(BaseModel):
    transcript: str
    language: DetectedLanguageOut
    stt_language: str | None
    duration_seconds: float | None
    stt_provider: str


class SpeechAudioOut(BaseModel):
    mime_type: str
    base64: str
    provider: str


class VoiceReplyOut(BaseModel):
    message: str  # full reply, as shown in the chat bubble
    speakable: str  # markdown-free, length-capped text for TTS
    language: DetectedLanguageOut
    voice_lang: str  # BCP-47 tag for picking a browser speechSynthesis voice
    references: list[ChatReferenceOut]
    tool_calls: list[ChatToolCallOut]
    provider: str
    audio: SpeechAudioOut | None = None
    tts_error: str | None = None  # set when audio was requested but synthesis failed (reply text still usable)
    action: ActionStateOut | None = None  # business-action draft / outcome (same flow as /chat)


class VoiceRespondRequest(BaseModel):
    """Second half of a voice turn, after /voice/transcribe: the transcript is
    already the last user message. Same validation as /chat."""

    messages: list[ChatMessageIn] = Field(min_length=1, max_length=50)
    language_mode: LanguageModeIn = "auto"
    tts: bool = False
    provider: str | None = None
    conversation_id: ConversationId | None = None
    pending_action: PendingActionIn | None = None


class VoiceTurnOut(VoiceReplyOut):
    transcript: str
    stt_language: str | None
    duration_seconds: float | None
    stt_provider: str


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    already_speakable: bool = False


class SpeakOut(BaseModel):
    speakable: str
    audio: SpeechAudioOut
