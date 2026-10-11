import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.services.ai.base import (
    ChatMessage,
    ProviderError,
    ProviderNotConfigured,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
    ToolCall,
    ToolSpec,
)
from app.services.ai.openai_compatible import OpenAICompatibleProvider
from app.services.ai.providers import build_provider, configured_providers
from app.services.ai.registry import get_provider


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def _run(coro):
    return asyncio.run(coro)


def _respond(monkeypatch, handler):
    """Patch httpx.AsyncClient.post to call `handler(url, json) -> httpx.Response` instead of hitting the network."""

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            return handler(url, json, headers)

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)


def test_chat_without_api_key_raises_not_configured():
    provider = OpenAICompatibleProvider("groq", "", "https://example.invalid", "some-model")
    with pytest.raises(ProviderNotConfigured):
        _run(provider.chat([ChatMessage(role="user", content="hi")]))


def test_chat_parses_plain_text_response(monkeypatch):
    def handler(url, payload, headers):
        assert payload["model"] == "some-model"
        assert payload["messages"][0]["role"] == "user"
        assert "tools" not in payload
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "42"}, "finish_reason": "stop"}]})

    _respond(monkeypatch, handler)
    provider = OpenAICompatibleProvider("groq", "fake-key", "https://example.invalid", "some-model")
    result = _run(provider.chat([ChatMessage(role="user", content="what is the answer?")]))
    assert result.message.content == "42"
    assert result.message.tool_calls == []
    assert result.finish_reason == "stop"


def test_chat_includes_tools_and_parses_tool_calls(monkeypatch):
    def handler(url, payload, headers):
        assert payload["tools"][0]["function"]["name"] == "list_records"
        assert payload["tool_choice"] == "auto"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "list_records", "arguments": '{"worksheet": "Projects"}'},
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        )

    _respond(monkeypatch, handler)
    provider = OpenAICompatibleProvider("groq", "fake-key", "https://example.invalid", "some-model")
    tools = [ToolSpec(name="list_records", description="List records", parameters={"type": "object", "properties": {}})]
    result = _run(provider.chat([ChatMessage(role="user", content="list projects")], tools=tools))
    assert result.finish_reason == "tool_calls"
    assert len(result.message.tool_calls) == 1
    call = result.message.tool_calls[0]
    assert call.name == "list_records"
    assert call.arguments == {"worksheet": "Projects"}


def test_assistant_message_with_tool_calls_serializes_correctly(monkeypatch):
    captured = {}

    def handler(url, payload, headers):
        captured["payload"] = payload
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]})

    _respond(monkeypatch, handler)
    provider = OpenAICompatibleProvider("groq", "fake-key", "https://example.invalid", "some-model")
    history = [
        ChatMessage(role="user", content="list projects"),
        ChatMessage(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(id="call_1", name="list_records", arguments={"worksheet": "Projects"})],
        ),
        ChatMessage(role="tool", tool_call_id="call_1", name="list_records", content='{"records": []}'),
    ]
    _run(provider.chat(history))
    sent = captured["payload"]["messages"]
    assert sent[1]["tool_calls"][0]["function"]["name"] == "list_records"
    assert sent[2]["role"] == "tool"
    assert sent[2]["tool_call_id"] == "call_1"


def _no_sleep(monkeypatch) -> list[float]:
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return slept


def test_429_raises_rate_limited_after_one_retry(monkeypatch):
    slept = _no_sleep(monkeypatch)
    calls = []

    def handler(url, payload, headers):
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "5"}, json={"error": "rate limited"})

    _respond(monkeypatch, handler)
    provider = OpenAICompatibleProvider("groq", "fake-key", "https://example.invalid", "some-model")
    with pytest.raises(ProviderRateLimited) as exc_info:
        _run(provider.chat([ChatMessage(role="user", content="hi")]))
    assert exc_info.value.retry_after == 5.0
    assert len(calls) == 2
    assert slept == [5.0]


def test_429_with_short_wait_retries_and_succeeds(monkeypatch):
    _no_sleep(monkeypatch)
    responses = [
        httpx.Response(429, headers={"retry-after": "2"}, json={"error": "rate limited"}),
        httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}),
    ]
    _respond(monkeypatch, lambda url, payload, headers: responses.pop(0))
    provider = OpenAICompatibleProvider("groq", "fake-key", "https://example.invalid", "some-model")
    result = _run(provider.chat([ChatMessage(role="user", content="hi")]))
    assert result.message.content == "ok"


def test_429_with_long_wait_fails_without_retry(monkeypatch):
    slept = _no_sleep(monkeypatch)

    def handler(url, payload, headers):
        return httpx.Response(429, headers={"retry-after": "60"}, json={"error": "rate limited"})

    _respond(monkeypatch, handler)
    provider = OpenAICompatibleProvider("groq", "fake-key", "https://example.invalid", "some-model")
    with pytest.raises(ProviderRateLimited):
        _run(provider.chat([ChatMessage(role="user", content="hi")]))
    assert slept == []


def test_cerebras_provider_reads_its_own_key():
    settings = _settings(chatbot_provider="cerebras", cerebras_api_key="fake-key")
    provider = get_provider(settings)
    assert provider.name == "cerebras"
    assert provider._model == "gpt-oss-120b"


def test_5xx_raises_unavailable(monkeypatch):
    def handler(url, payload, headers):
        return httpx.Response(503, json={"error": "down"})

    _respond(monkeypatch, handler)
    provider = OpenAICompatibleProvider("groq", "fake-key", "https://example.invalid", "some-model")
    with pytest.raises(ProviderUnavailable):
        _run(provider.chat([ChatMessage(role="user", content="hi")]))


def test_other_4xx_raises_provider_error(monkeypatch):
    def handler(url, payload, headers):
        return httpx.Response(400, json={"error": "bad model"})

    _respond(monkeypatch, handler)
    provider = OpenAICompatibleProvider("groq", "fake-key", "https://example.invalid", "some-model")
    with pytest.raises(ProviderError):
        _run(provider.chat([ChatMessage(role="user", content="hi")]))


def test_timeout_raises_provider_timeout(monkeypatch):
    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    provider = OpenAICompatibleProvider("groq", "fake-key", "https://example.invalid", "some-model")
    with pytest.raises(ProviderTimeout):
        _run(provider.chat([ChatMessage(role="user", content="hi")]))


def test_build_provider_returns_none_when_no_key():
    settings = _settings(groq_api_key="")
    assert build_provider("groq", settings) is None


def test_build_provider_returns_configured_provider():
    settings = _settings(groq_api_key="fake-key")
    provider = build_provider("groq", settings)
    assert provider is not None
    assert provider.name == "groq"


def test_configured_providers_lists_only_ones_with_keys():
    settings = _settings(groq_api_key="x", gemini_api_key="", openrouter_api_key="y")
    assert set(configured_providers(settings)) == {"groq", "openrouter"}


def test_get_provider_falls_back_when_default_has_no_key():
    settings = _settings(chatbot_provider="groq", groq_api_key="", gemini_api_key="fake-key")
    provider = get_provider(settings)
    assert provider.name == "gemini"


def test_get_provider_raises_clear_error_naming_env_var_when_nothing_configured():
    settings = _settings(groq_api_key="", gemini_api_key="", openrouter_api_key="")
    with pytest.raises(ProviderNotConfigured) as exc_info:
        get_provider(settings)
    assert "GROQ_API_KEY" in str(exc_info.value)


def test_gemini_key_read_from_vedha_style_env_var(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY_1", "fake-key")
    assert _settings().gemini_api_key == "fake-key"


def test_gemini_key_read_from_conventional_env_var(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY_1", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    assert _settings().gemini_api_key == "fake-key"


def test_chatbot_model_override_applies_to_configured_provider():
    settings = _settings(chatbot_provider="groq", groq_api_key="fake-key", chatbot_model="custom-model")
    assert build_provider("groq", settings)._model == "custom-model"


def test_fallback_provider_ignores_other_providers_model_override():
    settings = _settings(chatbot_provider="groq", groq_api_key="", gemini_api_key="fake-key", chatbot_model="groq-only-model")
    provider = get_provider(settings)
    assert provider.name == "gemini"
    assert provider._model == "gemini-flash-latest"


def test_gemini_thought_signature_is_echoed_back(monkeypatch):
    signature = {"google": {"thought_signature": "opaque-sig"}}
    sent_payloads = []
    responses = [
        httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "list_entities", "arguments": "{}"},
             "extra_content": signature}]}}]}),
        httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "done"}}]}),
    ]

    def handler(url, payload, headers):
        sent_payloads.append(payload)
        return responses.pop(0)

    _respond(monkeypatch, handler)
    provider = OpenAICompatibleProvider("gemini", "fake-key", "https://example.invalid", "some-model")
    first = _run(provider.chat([ChatMessage(role="user", content="hi")]))
    assert first.message.tool_calls[0].extra_content == signature

    history = [
        ChatMessage(role="user", content="hi"),
        first.message,
        ChatMessage(role="tool", tool_call_id="c1", name="list_entities", content="{}"),
    ]
    _run(provider.chat(history))
    assert sent_payloads[1]["messages"][1]["tool_calls"][0]["extra_content"] == signature
