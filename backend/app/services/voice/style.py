"""Inject voice-mode instructions into the existing chat orchestrator without modifying it.

``run_chat_turn`` builds its own system prompt; wrapping the provider lets
the voice pipeline (a) append "reply in the user's language, briefly, no
markdown" to that system message and (b) add a short language reminder to
the latest user turn, on every LLM call of the turn (tool iterations
included), while tools, validation and grounding stay identical to text chat.
Neither change is ever returned to the client or stored.
"""

from dataclasses import replace

from app.services.ai.base import ChatMessage, ChatResult, LLMProvider, ProviderError, ToolSpec

# Groq validates tool-call arguments server-side and rejects the whole
# completion when the model emits e.g. ``"field": null`` for a count (the
# aggregate tool's schema types ``field`` as a plain string). The model
# usually gets it right on a second sample, so retry exactly once.
_RETRYABLE_MARKERS = ("tool call validation failed", "tool_use_failed", "failed to call a function")


def _is_retryable(exc: ProviderError) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _RETRYABLE_MARKERS)


class VoiceStyleProvider:
    def __init__(self, inner: LLMProvider, instruction: str, reminder: str | None = None):
        self._inner = inner
        self._instruction = instruction
        self._reminder = reminder
        self.name = inner.name

    def _styled(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        if messages and messages[0].role == "system":
            out = [replace(messages[0], content=f"{messages[0].content}\n\n{self._instruction}"), *messages[1:]]
        else:
            out = [ChatMessage(role="system", content=self._instruction), *messages]
        if self._reminder:
            for i in range(len(out) - 1, -1, -1):
                if out[i].role == "user":
                    out[i] = replace(out[i], content=f"{out[i].content}\n\n{self._reminder}")
                    break
        return out

    async def chat(self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None) -> ChatResult:
        styled = self._styled(messages)
        try:
            return await self._inner.chat(styled, tools)
        except ProviderError as exc:
            if type(exc) is not ProviderError or not _is_retryable(exc):
                raise
            return await self._inner.chat(styled, tools)
