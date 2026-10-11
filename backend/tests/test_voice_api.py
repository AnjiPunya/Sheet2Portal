"""Voice endpoint tests. All outbound STT/TTS HTTP goes through a MockTransport
and the LLM is scripted -- no real keys or network are ever used."""

import base64
import json
import uuid

import pytest

from app.services.ai.base import ChatMessage, ChatResult, ProviderRateLimited, ToolCall
from app.services.voice.audio import pcm_to_wav
from tests.voice_helpers import WEBM_AUDIO, FakeVoiceAPIs

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _upload(client, path, tenant=None):
    with open(path, "rb") as f:
        headers = {"X-Tenant-Id": tenant} if tenant else {}
        return client.post("/api/workbooks", files={"file": ("workbook.xlsx", f, XLSX)}, headers=headers).json()["id"]


class RecordingProvider:
    """Scripted LLM that records the messages it was sent on every call."""

    name = "fake"

    def __init__(self, results):
        self._results = list(results)
        self.calls: list[list[ChatMessage]] = []

    async def chat(self, messages, tools=None):
        self.calls.append(list(messages))
        return self._results.pop(0)


class RaisingProvider:
    name = "fake"

    def __init__(self, exc):
        self._exc = exc

    async def chat(self, messages, tools=None):
        raise self._exc


def _answer(text):
    return ChatResult(message=ChatMessage(role="assistant", content=text), finish_reason="stop")


def _patch_llm(monkeypatch, provider):
    from app.api.routes import voice as voice_route

    monkeypatch.setattr(voice_route, "get_provider", lambda settings, requested=None: provider)


@pytest.fixture
def keys(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test-groq-key")
    monkeypatch.setattr(settings, "gemini_api_key", "test-gemini-key")


@pytest.fixture
def apis(monkeypatch):
    return FakeVoiceAPIs().install(monkeypatch)


def _turn(client, workbook_id, audio=WEBM_AUDIO, **form):
    return client.post(
        f"/api/workbooks/{workbook_id}/voice/turn",
        files={"audio": ("speech.webm", audio, "audio/webm;codecs=opus")},
        data={k: (json.dumps(v) if k == "history" else str(v)) for k, v in form.items()},
    )


# --- language handling ------------------------------------------------------


@pytest.mark.parametrize(
    "transcript,whisper_lang,expected_lang,instruction_marker,voice_lang",
    [
        ("మొత్తం బడ్జెట్ ఎంత?", "telugu", "te", "Telugu script", "te-IN"),
        ("What is the total budget?", "english", "en", "clear, simple English", "en-IN"),
        ("Projects లో total budget ఎంత?", "english", "mixed", "Tenglish", "te-IN"),
    ],
)
def test_voice_turn_replies_in_users_language(
    client, multi_sheet_xlsx, keys, apis, monkeypatch, transcript, whisper_lang, expected_lang, instruction_marker, voice_lang
):
    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq(transcript, language=whisper_lang)
    llm = RecordingProvider([_answer("**Total budget** is 35000 (Projects → Budget).")])
    _patch_llm(monkeypatch, llm)

    response = _turn(client, workbook_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transcript"] == transcript
    assert body["language"] == expected_lang
    assert body["voice_lang"] == voice_lang
    assert body["stt_provider"] == "groq"
    assert body["message"].startswith("**Total budget**")
    assert "**" not in body["speakable"]
    assert body["audio"] is None  # not requested

    system = llm.calls[0][0]
    assert system.role == "system"
    assert "data assistant" in system.content  # orchestrator's own prompt kept
    assert instruction_marker in system.content
    last_user = llm.calls[0][-1]
    assert last_user.role == "user" and last_user.content.startswith(transcript)
    assert "(Voice reply:" in last_user.content  # per-turn language reminder, server-side only


def test_auto_mode_sends_codemixed_prompt_and_no_language(client, multi_sheet_xlsx, keys, apis, monkeypatch):
    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq("total budget ఎంత?")
    _patch_llm(monkeypatch, RecordingProvider([_answer("35000")]))

    assert _turn(client, workbook_id, language_mode="auto").status_code == 200
    form = apis.groq_form().decode("utf-8", "ignore")
    assert 'name="language"' not in form
    assert "whisper-large-v3" in form
    assert "ఎంత" in form  # code-mixed style hint
    assert "Budget" in form and "Projects" in form  # workbook vocabulary
    auth = [r for r in apis.requests if "groq" in str(r.url)][0].headers["authorization"]
    assert auth == "Bearer test-groq-key"


def test_telugu_mode_forces_language_te(client, multi_sheet_xlsx, keys, apis, monkeypatch):
    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq("బడ్జెట్ ఎంత?")
    _patch_llm(monkeypatch, RecordingProvider([_answer("35000")]))
    assert _turn(client, workbook_id, language_mode="te").status_code == 200
    form = apis.groq_form().decode("utf-8", "ignore")
    assert 'name="language"\r\n\r\nte' in form


def test_auto_mode_retries_as_telugu_when_whisper_guesses_other_language(client, multi_sheet_xlsx, keys, apis, monkeypatch):
    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq("પ્રોજેક્ટ", language="gujarati").groq("Projects లో budget ఎంత?", language="telugu")
    _patch_llm(monkeypatch, RecordingProvider([_answer("35000")]))

    body = _turn(client, workbook_id).json()
    assert body["transcript"] == "Projects లో budget ఎంత?"
    assert body["language"] == "mixed"
    assert 'name="language"\r\n\r\nte' in apis.groq_form(1).decode("utf-8", "ignore")


# --- conversation + tools ---------------------------------------------------


def test_follow_up_history_is_forwarded(client, multi_sheet_xlsx, keys, apis, monkeypatch):
    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq("mari Mobile App di entha?", language="english")
    llm = RecordingProvider([_answer("Mobile App budget 25000.")])
    _patch_llm(monkeypatch, llm)

    history = [
        {"role": "user", "content": "Website Revamp budget entha?"},
        {"role": "assistant", "content": "Website Revamp budget 10000."},
    ]
    body = _turn(client, workbook_id, history=history).json()
    sent = [(m.role, m.content.split("\n\n(Voice reply:")[0]) for m in llm.calls[0][1:]]
    assert sent == [
        ("user", "Website Revamp budget entha?"),
        ("assistant", "Website Revamp budget 10000."),
        ("user", "mari Mobile App di entha?"),
    ]
    # only the latest user turn carries the reminder
    assert "(Voice reply:" not in llm.calls[0][1].content
    assert "Telugu-English mix" in llm.calls[0][3].content
    assert body["language"] == "mixed"


def test_voice_turn_runs_workbook_tools(client, multi_sheet_xlsx, keys, apis, monkeypatch):
    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq("Projects లో total budget ఎంత?")
    call = ToolCall(id="c1", name="aggregate", arguments={"worksheet": "Projects", "operation": "sum", "field": "Budget"})
    llm = RecordingProvider(
        [
            ChatResult(message=ChatMessage(role="assistant", tool_calls=[call]), finish_reason="tool_calls"),
            _answer("Projects లో total budget 35000."),
        ]
    )
    _patch_llm(monkeypatch, llm)

    body = _turn(client, workbook_id).json()
    assert body["tool_calls"] == [{"name": "aggregate", "arguments": call.arguments}]
    tool_msg = [m for m in llm.calls[1] if m.role == "tool"][0]
    assert json.loads(tool_msg.content)["value"] == 35000
    # voice instruction applied on every LLM call of the turn, incl. after tools
    assert "Tenglish" in llm.calls[1][0].content
    assert body["speakable"] == "Projects లో total budget 35000."


def test_groq_tool_validation_400_is_retried_once(client, multi_sheet_xlsx, keys, apis, monkeypatch):
    from app.services.ai.base import ProviderError

    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq("pending tasks ఎన్ని?")

    class FlakyToolProvider(RecordingProvider):
        async def chat(self, messages, tools=None):
            self.calls.append(list(messages))
            if len(self.calls) == 1:
                raise ProviderError('groq returned HTTP 400: {"error":{"message":"Tool call validation failed: ..."}}')
            return _answer("1 pending task ఉంది.")

    llm = FlakyToolProvider([])
    _patch_llm(monkeypatch, llm)
    r = _turn(client, workbook_id)
    assert r.status_code == 200
    assert len(llm.calls) == 2


def test_other_provider_errors_are_not_retried(client, multi_sheet_xlsx, keys, apis, monkeypatch):
    from app.services.ai.base import ProviderError

    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq("hello", language="english")
    _patch_llm(monkeypatch, RaisingProvider(ProviderError("groq returned HTTP 400: context too long")))
    r = _turn(client, workbook_id)
    assert r.status_code == 502
    assert r.json()["detail"]["error_code"] == "PROVIDER_ERROR"


def test_transcribe_then_respond_flow(client, multi_sheet_xlsx, keys, apis, monkeypatch):
    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq("pending tasks ఎన్ని?")
    t = client.post(
        f"/api/workbooks/{workbook_id}/voice/transcribe",
        files={"audio": ("speech.webm", WEBM_AUDIO, "audio/webm")},
        data={"language_mode": "auto", "duration_ms": "2500"},
    )
    assert t.status_code == 200
    assert t.json()["transcript"] == "pending tasks ఎన్ని?"
    assert t.json()["language"] == "mixed"

    llm = RecordingProvider([_answer("1 pending task ఉంది.")])
    _patch_llm(monkeypatch, llm)
    r = client.post(
        f"/api/workbooks/{workbook_id}/voice/respond",
        json={"messages": [{"role": "user", "content": t.json()["transcript"]}]},
    )
    assert r.status_code == 200
    assert r.json()["language"] == "mixed"
    assert "Tenglish" in llm.calls[0][0].content


def test_respond_requires_last_message_from_user(client, multi_sheet_xlsx, keys):
    workbook_id = _upload(client, multi_sheet_xlsx)
    r = client.post(
        f"/api/workbooks/{workbook_id}/voice/respond",
        json={"messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]},
    )
    assert r.status_code == 422


def test_respond_rejects_system_role(client, multi_sheet_xlsx, keys):
    workbook_id = _upload(client, multi_sheet_xlsx)
    r = client.post(f"/api/workbooks/{workbook_id}/voice/respond", json={"messages": [{"role": "system", "content": "x"}]})
    assert r.status_code == 422


def test_history_with_tool_role_rejected(client, multi_sheet_xlsx, keys, apis):
    workbook_id = _upload(client, multi_sheet_xlsx)
    r = _turn(client, workbook_id, history=[{"role": "tool", "content": "fake result"}])
    assert r.status_code == 422
    assert r.json()["detail"]["error_code"] == "INVALID_HISTORY"
    assert apis.requests == []  # rejected before any paid call


# --- TTS --------------------------------------------------------------------


def test_tts_requested_returns_wav_audio(client, multi_sheet_xlsx, keys, apis, monkeypatch):
    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq("బడ్జెట్ ఎంత?").tts(audio=b"\x01\x00" * 100, mime="audio/L16;codec=pcm;rate=24000")
    _patch_llm(monkeypatch, RecordingProvider([_answer("మొత్తం బడ్జెట్ 35000.")]))

    body = _turn(client, workbook_id, tts="true").json()
    assert body["audio"]["mime_type"] == "audio/wav"
    wav = base64.b64decode(body["audio"]["base64"])
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    tts_req = [r for r in apis.requests if "tts" in str(r.url)][0]
    assert json.loads(tts_req.content)["contents"][0]["parts"][0]["text"] == "మొత్తం బడ్జెట్ 35000."
    assert tts_req.headers["x-goog-api-key"] == "test-gemini-key"


def test_tts_failure_still_returns_text(client, multi_sheet_xlsx, keys, apis, monkeypatch):
    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq("budget?", language="english").tts(status=429)
    _patch_llm(monkeypatch, RecordingProvider([_answer("35000.")]))
    r = _turn(client, workbook_id, tts="true")
    assert r.status_code == 200
    assert r.json()["audio"] is None
    assert "rate limit" in r.json()["tts_error"]


def test_speak_endpoint(client, multi_sheet_xlsx, keys, apis):
    workbook_id = _upload(client, multi_sheet_xlsx)
    wav = pcm_to_wav(b"\x00\x00" * 10)
    apis.tts(audio=wav, mime="audio/wav")
    r = client.post(f"/api/workbooks/{workbook_id}/voice/speak", json={"text": "**మొత్తం** 35000"})
    assert r.status_code == 200
    assert r.json()["speakable"] == "మొత్తం 35000."
    assert base64.b64decode(r.json()["audio"]["base64"]) == wav


def test_speak_without_gemini_key_is_503(client, multi_sheet_xlsx):
    workbook_id = _upload(client, multi_sheet_xlsx)
    r = client.post(f"/api/workbooks/{workbook_id}/voice/speak", json={"text": "hello"})
    assert r.status_code == 503
    assert "GEMINI_API_KEY" in r.json()["detail"]["message"]


# --- errors -----------------------------------------------------------------


def test_missing_stt_keys_returns_503(client, multi_sheet_xlsx, apis):
    workbook_id = _upload(client, multi_sheet_xlsx)
    r = _turn(client, workbook_id)
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["error_code"] == "VOICE_NOT_CONFIGURED"
    assert "GROQ_API_KEY" in detail["message"]


def test_missing_llm_key_returns_503(client, multi_sheet_xlsx, monkeypatch, apis):
    from app.core.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "only-for-stt")
    monkeypatch.setattr("app.api.routes.voice.get_provider", _raise_not_configured)
    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq("hello", language="english")
    r = _turn(client, workbook_id)
    assert r.status_code == 503
    assert r.json()["detail"]["error_code"] == "CHATBOT_NOT_CONFIGURED"


def _raise_not_configured(settings, requested=None):
    from app.services.ai.base import ProviderNotConfigured

    raise ProviderNotConfigured("No chatbot provider is configured. Set GROQ_API_KEY")


def test_stt_rate_limit_returns_429_with_retry_after(client, multi_sheet_xlsx, monkeypatch, apis):
    from app.core.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "k")  # no Gemini -> no fallback
    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq_status(429, headers={"retry-after": "7"})
    r = _turn(client, workbook_id)
    assert r.status_code == 429
    assert r.json()["detail"]["error_code"] == "PROVIDER_RATE_LIMITED"
    assert r.headers["retry-after"] == "7"


def test_stt_rate_limit_falls_back_to_gemini(client, multi_sheet_xlsx, keys, apis, monkeypatch):
    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq_status(429).gemini_stt("Projects లో budget ఎంత?", "mixed")
    _patch_llm(monkeypatch, RecordingProvider([_answer("35000")]))
    body = _turn(client, workbook_id).json()
    assert body["stt_provider"] == "gemini"
    assert body["language"] == "mixed"


def test_llm_rate_limit_returns_429(client, multi_sheet_xlsx, keys, apis, monkeypatch):
    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq("hello", language="english")
    _patch_llm(monkeypatch, RaisingProvider(ProviderRateLimited("fake", retry_after=2.0)))
    r = _turn(client, workbook_id)
    assert r.status_code == 429
    assert r.headers["retry-after"] == "2"


def test_stt_timeout_returns_504(client, multi_sheet_xlsx, keys, monkeypatch):
    import httpx

    from app.services.voice import http as voice_http

    def boom(request):
        raise httpx.ReadTimeout("slow", request=request)

    real = httpx.AsyncClient
    monkeypatch.setattr(voice_http, "client_factory", lambda **kw: real(transport=httpx.MockTransport(boom), **kw))
    workbook_id = _upload(client, multi_sheet_xlsx)
    r = _turn(client, workbook_id)
    assert r.status_code == 504
    assert r.json()["detail"]["error_code"] == "PROVIDER_TIMEOUT"


def test_provider_rejecting_audio_is_422(client, multi_sheet_xlsx, keys, apis):
    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq_status(400)
    r = _turn(client, workbook_id)
    assert r.status_code == 422
    assert r.json()["detail"]["error_code"] == "AUDIO_UNREADABLE"


def test_empty_audio_rejected_without_calling_stt(client, multi_sheet_xlsx, keys, apis):
    workbook_id = _upload(client, multi_sheet_xlsx)
    r = _turn(client, workbook_id, audio=b"")
    assert r.status_code == 422
    assert r.json()["detail"]["error_code"] == "EMPTY_AUDIO"
    assert apis.requests == []


def test_silent_audio_is_no_speech(client, multi_sheet_xlsx, keys, apis, monkeypatch):
    workbook_id = _upload(client, multi_sheet_xlsx)
    apis.groq("Thank you.", language="english", no_speech=0.85)
    llm = RecordingProvider([])
    _patch_llm(monkeypatch, llm)
    r = _turn(client, workbook_id)
    assert r.status_code == 422
    assert r.json()["detail"]["error_code"] == "NO_SPEECH_DETECTED"
    assert llm.calls == []  # no LLM quota spent on silence


def test_oversize_audio_rejected(client, multi_sheet_xlsx, keys, apis):
    from app.services.voice.settings import voice_settings

    workbook_id = _upload(client, multi_sheet_xlsx)
    big = b"\x1aE\xdf\xa3" + b"\x00" * (voice_settings.max_audio_bytes + 10)
    r = _turn(client, workbook_id, audio=big)
    assert r.status_code == 413
    assert r.json()["detail"]["error_code"] == "AUDIO_TOO_LARGE"
    assert apis.requests == []


def test_too_long_declared_duration_rejected(client, multi_sheet_xlsx, keys, apis):
    workbook_id = _upload(client, multi_sheet_xlsx)
    r = _turn(client, workbook_id, duration_ms=120_000)
    assert r.status_code == 413
    assert r.json()["detail"]["error_code"] == "AUDIO_TOO_LONG"


def test_too_long_wav_rejected(client, multi_sheet_xlsx, keys, apis, monkeypatch):
    from app.services.voice.settings import voice_settings

    monkeypatch.setattr(voice_settings, "max_audio_seconds", 1.0)
    workbook_id = _upload(client, multi_sheet_xlsx)
    wav = pcm_to_wav(b"\x00\x00" * 16000 * 4, sample_rate=16000)  # 4 seconds
    r = _turn(client, workbook_id, audio=wav)
    assert r.status_code == 413


def test_unsupported_format_rejected(client, multi_sheet_xlsx, keys, apis):
    workbook_id = _upload(client, multi_sheet_xlsx)
    r = _turn(client, workbook_id, audio=b"%PDF-1.4" + b"\x00" * 2000)
    assert r.status_code == 415
    assert r.json()["detail"]["error_code"] == "UNSUPPORTED_AUDIO_FORMAT"


def test_other_tenants_workbook_is_404(client, multi_sheet_xlsx, keys, apis):
    workbook_id = _upload(client, multi_sheet_xlsx, tenant="tenant-a")
    r = client.post(
        f"/api/workbooks/{workbook_id}/voice/turn",
        files={"audio": ("speech.webm", WEBM_AUDIO, "audio/webm")},
        headers={"X-Tenant-Id": "tenant-b"},
    )
    assert r.status_code == 404
    for path in ("transcribe",):
        r = client.post(
            f"/api/workbooks/{workbook_id}/voice/{path}",
            files={"audio": ("speech.webm", WEBM_AUDIO, "audio/webm")},
            headers={"X-Tenant-Id": "tenant-b"},
        )
        assert r.status_code == 404
    r = client.post(
        f"/api/workbooks/{workbook_id}/voice/speak", json={"text": "hi"}, headers={"X-Tenant-Id": "tenant-b"}
    )
    assert r.status_code == 404
    assert apis.requests == []  # no STT/TTS quota spent for unauthorized callers


def test_unknown_workbook_is_404(client, keys, apis):
    r = _turn(client, uuid.uuid4())
    assert r.status_code == 404


def test_voice_disabled(client, multi_sheet_xlsx, keys, apis, monkeypatch):
    from app.services.voice.settings import voice_settings

    monkeypatch.setattr(voice_settings, "enabled", False)
    workbook_id = _upload(client, multi_sheet_xlsx)
    assert _turn(client, workbook_id).status_code == 503


# --- capabilities -----------------------------------------------------------


def test_capabilities_never_expose_keys(client, keys):
    r = client.get("/api/voice/capabilities")
    assert r.status_code == 200
    body = r.json()
    assert body["stt_available"] is True
    assert body["stt_providers"] == ["groq", "gemini"]
    assert body["server_tts_available"] is True
    assert body["language_modes"] == ["auto", "te", "en"]
    assert "test-groq-key" not in r.text and "test-gemini-key" not in r.text


def test_capabilities_without_keys(client):
    body = client.get("/api/voice/capabilities").json()
    assert body["stt_available"] is False
    assert body["server_tts_available"] is False
