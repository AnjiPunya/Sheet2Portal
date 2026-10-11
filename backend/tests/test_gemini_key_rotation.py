"""GEMINI_API_KEY_2: a second Gemini key tried when the first is rate limited
or out of quota, before the chat route falls back to the next provider.

The HTTP layer is faked -- no network, no real keys. Responses are chosen by
the endpoint + Bearer token each request carries, so the tests can assert
exactly which key/provider was tried, in which order.
"""

import asyncio
import logging

import httpx
import pytest

from app.core.config import Settings
from app.services.ai.base import ChatMessage, ProviderRateLimited, ProviderUnavailable
from app.services.ai.providers import GEMINI_URL, GROQ_URL, build_provider, configured_providers

KEY_1 = "test-gemini-key-one"
KEY_2 = "test-gemini-key-two"
GROQ_KEY = "test-groq-key"

OK = {"choices": [{"message": {"content": "answer"}, "finish_reason": "stop"}]}


def _settings(**overrides) -> Settings:
    base = {"chatbot_provider": "gemini", "gemini_api_key": KEY_1, "gemini_api_key_2": KEY_2}
    return Settings(_env_file=None, **{**base, **overrides})


def _run(coro):
    return asyncio.run(coro)


class FakeHTTP:
    """Patches httpx.AsyncClient; `responses` maps (url, key) -> status code."""

    def __init__(self, monkeypatch, responses: dict[tuple[str, str], int]):
        self.calls: list[tuple[str, str]] = []
        fake = self

        class Client:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, headers=None, json=None):
                key = headers["Authorization"].removeprefix("Bearer ")
                fake.calls.append((url, key))
                status = responses[(url, key)]
                body = OK if status == 200 else {"error": {"code": status, "status": "RESOURCE_EXHAUSTED"}}
                return httpx.Response(status, json=body)

        monkeypatch.setattr(httpx, "AsyncClient", Client)

    @property
    def keys_tried(self) -> list[str]:
        return [key for _, key in self.calls]


async def _no_sleep(seconds):  # the single short-wait retry must not slow tests
    return None


@pytest.fixture(autouse=True)
def _instant_sleep(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)


def _ask(provider):
    return _run(provider.chat([ChatMessage(role="user", content="How many projects?")]))


# --- provider level ----------------------------------------------------------


def test_primary_key_success_never_touches_second_key(monkeypatch):
    http = FakeHTTP(monkeypatch, {(GEMINI_URL, KEY_1): 200, (GEMINI_URL, KEY_2): 200})
    result = _ask(build_provider("gemini", _settings()))
    assert result.message.content == "answer"
    assert http.keys_tried == [KEY_1]


def test_quota_on_primary_retries_with_second_key(monkeypatch):
    http = FakeHTTP(monkeypatch, {(GEMINI_URL, KEY_1): 429, (GEMINI_URL, KEY_2): 200})
    result = _ask(build_provider("gemini", _settings()))
    assert result.message.content == "answer"
    assert http.keys_tried == [KEY_1, KEY_2]


def test_rest_of_turn_skips_the_rate_limited_key(monkeypatch):
    # A chat turn makes several calls on one provider instance (tool call,
    # then final answer); once key 1 is limited, don't keep retrying it.
    http = FakeHTTP(monkeypatch, {(GEMINI_URL, KEY_1): 429, (GEMINI_URL, KEY_2): 200})
    provider = build_provider("gemini", _settings())
    _ask(provider)
    _ask(provider)
    assert http.keys_tried == [KEY_1, KEY_2, KEY_2]


def test_next_request_tries_the_primary_key_again(monkeypatch):
    http = FakeHTTP(monkeypatch, {(GEMINI_URL, KEY_1): 429, (GEMINI_URL, KEY_2): 200})
    _ask(build_provider("gemini", _settings()))
    _ask(build_provider("gemini", _settings()))  # providers are built per request
    assert http.keys_tried == [KEY_1, KEY_2, KEY_1, KEY_2]


def test_both_keys_rate_limited_raises_rate_limited(monkeypatch):
    http = FakeHTTP(monkeypatch, {(GEMINI_URL, KEY_1): 429, (GEMINI_URL, KEY_2): 429})
    with pytest.raises(ProviderRateLimited) as exc_info:
        _ask(build_provider("gemini", _settings()))
    assert http.keys_tried == [KEY_1, KEY_2]
    assert KEY_1 not in str(exc_info.value) and KEY_2 not in str(exc_info.value)


def test_non_quota_error_does_not_rotate_keys(monkeypatch):
    # A 5xx is the provider being down, not this key's quota -- a second key
    # won't help, so it's left to the route's provider fallback.
    http = FakeHTTP(monkeypatch, {(GEMINI_URL, KEY_1): 503, (GEMINI_URL, KEY_2): 200})
    with pytest.raises(ProviderUnavailable):
        _ask(build_provider("gemini", _settings()))
    assert http.keys_tried == [KEY_1]


def test_without_second_key_behaviour_is_unchanged(monkeypatch):
    http = FakeHTTP(monkeypatch, {(GEMINI_URL, KEY_1): 429})
    with pytest.raises(ProviderRateLimited):
        _ask(build_provider("gemini", _settings(gemini_api_key_2="")))
    assert http.keys_tried == [KEY_1]


def test_second_key_alone_still_configures_gemini(monkeypatch):
    settings = _settings(gemini_api_key="")
    assert "gemini" in configured_providers(settings)
    http = FakeHTTP(monkeypatch, {(GEMINI_URL, KEY_2): 200})
    _ask(build_provider("gemini", settings))
    assert http.keys_tried == [KEY_2]


def test_duplicate_second_key_is_not_retried(monkeypatch):
    http = FakeHTTP(monkeypatch, {(GEMINI_URL, KEY_1): 429})
    with pytest.raises(ProviderRateLimited):
        _ask(build_provider("gemini", _settings(gemini_api_key_2=KEY_1)))
    assert http.keys_tried == [KEY_1]


def test_rotation_logs_key_positions_never_values(monkeypatch, caplog):
    FakeHTTP(monkeypatch, {(GEMINI_URL, KEY_1): 429, (GEMINI_URL, KEY_2): 200})
    with caplog.at_level(logging.WARNING, logger="app.services.ai.openai_compatible"):
        _ask(build_provider("gemini", _settings()))
    assert "key #1 rate limited; retrying with key #2" in caplog.text
    assert KEY_1 not in caplog.text and KEY_2 not in caplog.text


def test_second_key_read_from_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY_2", "from-env")
    assert Settings(_env_file=None).gemini_api_key_2 == "from-env"


# --- chat route: both keys fail -> next provider ------------------------------


def _configure(monkeypatch, **fields):
    from app.core.config import settings

    for name, value in fields.items():
        monkeypatch.setattr(settings, name, value)


def _upload(client, path):
    with open(path, "rb") as f:
        return client.post("/api/workbooks", files={"file": ("w.xlsx", f, "application/octet-stream")}).json()["id"]


def _chat(client, workbook_id):
    return client.post(f"/api/workbooks/{workbook_id}/chat", json={"messages": [{"role": "user", "content": "hi"}]})


def test_chat_falls_back_to_groq_after_both_gemini_keys_hit_quota(client, multi_sheet_xlsx, monkeypatch):
    workbook_id = _upload(client, multi_sheet_xlsx)
    _configure(monkeypatch, chatbot_provider="gemini", gemini_api_key=KEY_1, gemini_api_key_2=KEY_2, groq_api_key=GROQ_KEY)
    http = FakeHTTP(monkeypatch, {(GEMINI_URL, KEY_1): 429, (GEMINI_URL, KEY_2): 429, (GROQ_URL, GROQ_KEY): 200})

    response = _chat(client, workbook_id)

    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "groq"
    assert http.calls == [(GEMINI_URL, KEY_1), (GEMINI_URL, KEY_2), (GROQ_URL, GROQ_KEY)]


def test_chat_uses_second_gemini_key_before_any_fallback(client, multi_sheet_xlsx, monkeypatch):
    workbook_id = _upload(client, multi_sheet_xlsx)
    _configure(monkeypatch, chatbot_provider="gemini", gemini_api_key=KEY_1, gemini_api_key_2=KEY_2, groq_api_key=GROQ_KEY)
    http = FakeHTTP(monkeypatch, {(GEMINI_URL, KEY_1): 429, (GEMINI_URL, KEY_2): 200, (GROQ_URL, GROQ_KEY): 200})

    response = _chat(client, workbook_id)

    assert response.json()["provider"] == "gemini"
    assert http.keys_tried == [KEY_1, KEY_2]


def test_chat_returns_429_when_every_key_and_provider_is_limited(client, multi_sheet_xlsx, monkeypatch):
    workbook_id = _upload(client, multi_sheet_xlsx)
    _configure(monkeypatch, chatbot_provider="gemini", gemini_api_key=KEY_1, gemini_api_key_2=KEY_2, groq_api_key=GROQ_KEY)
    FakeHTTP(monkeypatch, {(GEMINI_URL, KEY_1): 429, (GEMINI_URL, KEY_2): 429, (GROQ_URL, GROQ_KEY): 429})

    response = _chat(client, workbook_id)

    assert response.status_code == 429
    assert response.json()["detail"]["error_code"] == "PROVIDER_RATE_LIMITED"
    for key in (KEY_1, KEY_2, GROQ_KEY):
        assert key not in response.text


def test_chat_with_groq_primary_still_tries_groq_first(client, multi_sheet_xlsx, monkeypatch):
    workbook_id = _upload(client, multi_sheet_xlsx)
    _configure(monkeypatch, chatbot_provider="groq", gemini_api_key=KEY_1, gemini_api_key_2=KEY_2, groq_api_key=GROQ_KEY)
    http = FakeHTTP(monkeypatch, {(GROQ_URL, GROQ_KEY): 200})

    response = _chat(client, workbook_id)

    assert response.json()["provider"] == "groq"
    assert http.calls == [(GROQ_URL, GROQ_KEY)]
