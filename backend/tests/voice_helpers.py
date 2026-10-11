"""Shared fakes for voice tests: a scripted HTTP transport for Groq/Gemini and fake audio clips."""

import base64
import json

import httpx

from app.services.voice import http as voice_http

WEBM_AUDIO = b"\x1aE\xdf\xa3" + b"\x00" * 4000


class FakeVoiceAPIs:
    """Routes outgoing STT/TTS requests to scripted responses and records them."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.groq_responses: list[httpx.Response] = []
        self.gemini_stt_responses: list[httpx.Response] = []
        self.tts_responses: list[httpx.Response] = []

    # --- scripting helpers -------------------------------------------------
    def groq(self, text: str, language: str = "telugu", no_speech: float = 0.05, duration: float = 3.0):
        self.groq_responses.append(
            httpx.Response(
                200,
                json={
                    "task": "transcribe",
                    "language": language,
                    "duration": duration,
                    "text": f" {text}",
                    "segments": [{"id": 0, "text": text, "no_speech_prob": no_speech}],
                },
            )
        )
        return self

    def groq_status(self, status: int, headers: dict | None = None):
        self.groq_responses.append(httpx.Response(status, headers=headers or {}, json={"error": {"message": "x"}}))
        return self

    def gemini_stt_status(self, status: int):
        self.gemini_stt_responses.append(httpx.Response(status, json={"error": {"message": "x"}}))
        return self

    def gemini_stt(self, text: str, language: str):
        body = {"candidates": [{"content": {"parts": [{"text": json.dumps({"text": text, "language": language})}]}}]}
        self.gemini_stt_responses.append(httpx.Response(200, json=body))
        return self

    def tts(self, audio: bytes = b"RIFF\x00\x00\x00\x00WAVEfmt ", mime: str = "audio/wav", status: int = 200):
        if status != 200:
            self.tts_responses.append(httpx.Response(status, json={"error": {"message": "x"}}))
            return self
        body = {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": mime, "data": base64.b64encode(audio).decode()}}]}}]}
        self.tts_responses.append(httpx.Response(200, json=body))
        return self

    # --- transport ---------------------------------------------------------
    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if "api.groq.com" in url:
            return self.groq_responses.pop(0)
        if "tts" in url:
            return self.tts_responses.pop(0)
        if "generativelanguage" in url:
            return self.gemini_stt_responses.pop(0)
        raise AssertionError(f"unexpected outbound request to {url}")

    def install(self, monkeypatch):
        real = httpx.AsyncClient
        monkeypatch.setattr(
            voice_http, "client_factory", lambda **kw: real(transport=httpx.MockTransport(self.handler), **kw)
        )
        return self

    def groq_form(self, index: int = 0) -> bytes:
        return [r for r in self.requests if "api.groq.com" in str(r.url)][index].content
