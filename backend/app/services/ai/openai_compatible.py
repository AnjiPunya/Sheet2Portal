"""A single HTTP client for any OpenAI-compatible chat-completions endpoint.

Groq, Google Gemini (via its OpenAI-compatible endpoint) and OpenRouter all
speak this same wire format, tool-calling included, so one implementation
backs all three provider adapters instead of three near-duplicates.
"""

import asyncio
import json

import httpx

from app.services.ai.base import (
    ChatMessage,
    ChatResult,
    ProviderError,
    ProviderNotConfigured,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
    ToolCall,
    ToolSpec,
)


def _message_to_payload(message: ChatMessage) -> dict:
    payload: dict = {"role": message.role}
    if message.content is not None:
        payload["content"] = message.content
    if message.role == "assistant" and message.tool_calls:
        payload["tool_calls"] = []
        for tc in message.tool_calls:
            entry: dict = {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            if tc.extra_content:
                entry["extra_content"] = tc.extra_content
            payload["tool_calls"].append(entry)
    if message.role == "tool":
        payload["tool_call_id"] = message.tool_call_id
        payload["name"] = message.name
    return payload


def _tool_to_payload(tool: ToolSpec) -> dict:
    return {
        "type": "function",
        "function": {"name": tool.name, "description": tool.description, "parameters": tool.parameters},
    }


def _parse_response(data: dict, provider: str) -> ChatResult:
    choices = data.get("choices") or []
    if not choices:
        raise ProviderError(f"{provider} returned no choices")
    choice = choices[0]
    raw_message = choice.get("message") or {}

    tool_calls: list[ToolCall] = []
    for tc in raw_message.get("tool_calls") or []:
        function = tc.get("function") or {}
        raw_args = function.get("arguments") or "{}"
        try:
            parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except json.JSONDecodeError:
            parsed_args = {}
        tool_calls.append(
            ToolCall(
                id=tc.get("id", ""),
                name=function.get("name", ""),
                arguments=parsed_args,
                extra_content=tc.get("extra_content"),
            )
        )

    message = ChatMessage(role="assistant", content=raw_message.get("content"), tool_calls=tool_calls)
    return ChatResult(message=message, finish_reason=choice.get("finish_reason", "stop"))


class OpenAICompatibleProvider:
    """Implements :class:`LLMProvider` against any OpenAI-style chat API."""

    def __init__(
        self,
        name: str,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 20.0,
        max_rate_limit_wait: float = 10.0,
    ):
        self.name = name
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._timeout = timeout
        self._max_rate_limit_wait = max_rate_limit_wait

    async def chat(self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None) -> ChatResult:
        if not self._api_key:
            raise ProviderNotConfigured(f"{self.name} is not configured (no API key)")

        try:
            return await self._chat_once(messages, tools)
        except ProviderRateLimited as exc:
            # Free tiers cap tokens per minute and usually ask for a wait of
            # only a few seconds -- retry once rather than failing the turn.
            if exc.retry_after is None or exc.retry_after > self._max_rate_limit_wait:
                raise
            await asyncio.sleep(exc.retry_after)
            return await self._chat_once(messages, tools)

    async def _chat_once(self, messages: list[ChatMessage], tools: list[ToolSpec] | None) -> ChatResult:
        payload: dict = {
            "model": self._model,
            "messages": [_message_to_payload(m) for m in messages],
        }
        if tools:
            payload["tools"] = [_tool_to_payload(t) for t in tools]
            payload["tool_choice"] = "auto"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._base_url,
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"{self.name} request timed out") from exc
        except httpx.RequestError as exc:
            raise ProviderUnavailable(f"{self.name} request failed: {exc}") from exc

        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            try:
                retry_seconds = float(retry_after) if retry_after else None
            except ValueError:  # an HTTP-date form we don't bother parsing
                retry_seconds = None
            raise ProviderRateLimited(self.name, retry_after=retry_seconds)
        if response.status_code >= 500:
            raise ProviderUnavailable(f"{self.name} returned HTTP {response.status_code}")
        if response.status_code >= 400:
            raise ProviderError(f"{self.name} returned HTTP {response.status_code}: {response.text[:200]}")

        return _parse_response(response.json(), self.name)
