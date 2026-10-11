"""Inject voice-mode instructions into the existing chat orchestrator without modifying it.

``run_chat_turn`` builds its own system prompt; wrapping the provider lets
the voice pipeline append "reply in the user's language, briefly, no
markdown" to that system message on every LLM call of the turn (tool
iterations included), while tools, validation and grounding stay identical
to text chat.
"""

from dataclasses import replace

from app.services.ai.base import ChatMessage, ChatResult, LLMProvider, ToolSpec


class VoiceStyleProvider:
    def __init__(self, inner: LLMProvider, instruction: str):
        self._inner = inner
        self._instruction = instruction
        self.name = inner.name

    async def chat(self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None) -> ChatResult:
        if messages and messages[0].role == "system":
            system = replace(messages[0], content=f"{messages[0].content}\n\n{self._instruction}")
            messages = [system, *messages[1:]]
        else:
            messages = [ChatMessage(role="system", content=self._instruction), *messages]
        return await self._inner.chat(messages, tools)
