from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.actions import ActionStateOut, ConversationId, PendingActionIn


class ChatMessageIn(BaseModel):
    # Only user/assistant roles are ever accepted from the client -- system
    # and tool messages are constructed server-side only, so a client can
    # never inject a fake "tool result" or override the system prompt.
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn] = Field(min_length=1, max_length=50)
    provider: str | None = None
    # Business actions (draft -> confirm -> execute) are available when the
    # client sends a conversation id; pending_action is the draft it shows.
    conversation_id: ConversationId | None = None
    pending_action: PendingActionIn | None = None


class ChatReferenceActionOut(BaseModel):
    kind: str  # "details" | "related"
    label: str  # "View details", "View Tasks"
    worksheet: str  # sheet the action opens
    count: int | None = None  # related records, for "related"


class ChatReferenceOut(BaseModel):
    worksheet: str
    record_id: str  # real record id: what links use
    label: str | None = None  # record name shown to the user
    entity_label: str | None = None  # "Project", "Feed Log"
    actions: list[ChatReferenceActionOut] = []


class ChatToolCallOut(BaseModel):
    name: str
    arguments: dict


class ChatResponseOut(BaseModel):
    message: str
    references: list[ChatReferenceOut]
    tool_calls: list[ChatToolCallOut]
    provider: str
    action: ActionStateOut | None = None


class ChatSuggestionsOut(BaseModel):
    suggestions: list[str]
