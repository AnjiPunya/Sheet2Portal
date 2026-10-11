from typing import Literal

from pydantic import BaseModel, Field


class ChatMessageIn(BaseModel):
    # Only user/assistant roles are ever accepted from the client -- system
    # and tool messages are constructed server-side only, so a client can
    # never inject a fake "tool result" or override the system prompt.
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn] = Field(min_length=1, max_length=50)
    provider: str | None = None


class ChatReferenceOut(BaseModel):
    worksheet: str
    record_id: str


class ChatToolCallOut(BaseModel):
    name: str
    arguments: dict


class ChatResponseOut(BaseModel):
    message: str
    references: list[ChatReferenceOut]
    tool_calls: list[ChatToolCallOut]
    provider: str


class ChatSuggestionsOut(BaseModel):
    suggestions: list[str]
