"""Provider-agnostic chat/tool-calling interface for the chatbot.

AI is used exclusively here -- nowhere else in the app. Every provider
implements the same `LLMProvider` protocol so the chatbot orchestration
layer (``app/services/ai/orchestrator.py``) never has to know which vendor
is behind it.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict
    # Opaque provider data that must be echoed back verbatim on the next
    # turn (Gemini's thought_signature lives here); never inspected.
    extra_content: dict | None = None


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None  # set when role == "tool"
    name: str | None = None  # tool name, set when role == "tool"


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON schema for the tool's arguments


@dataclass
class ChatResult:
    message: ChatMessage
    finish_reason: str


class ProviderError(Exception):
    """Base class for provider-level failures. Never includes the API key."""


class ProviderNotConfigured(ProviderError):
    """No API key is available for this provider in the current environment."""


class ProviderRateLimited(ProviderError):
    def __init__(self, provider: str, retry_after: float | None = None):
        super().__init__(f"{provider} rate limit reached")
        self.provider = provider
        self.retry_after = retry_after


class ProviderTimeout(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    """Network failure or 5xx from the provider."""


class LLMProvider(Protocol):
    name: str

    async def chat(self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None) -> ChatResult:
        """Send a chat turn, optionally offering tools, and return the assistant's response."""
        ...
