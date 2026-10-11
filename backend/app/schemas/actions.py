from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

ActionStateName = Literal["clarification_required", "awaiting_confirmation", "completed", "cancelled", "failed"]

# Client-generated conversation ids (crypto.randomUUID() or hex).
ConversationId = Annotated[str, StringConstraints(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")]


class PendingActionIn(BaseModel):
    """The draft the client is currently showing; a plain "yes" confirms exactly this one."""

    draft_id: str = Field(max_length=64)
    token: str = Field(max_length=128)


class ActionConfirmIn(BaseModel):
    token: str = Field(max_length=128)
    conversation_id: ConversationId | None = None
    language: Literal["en", "te", "mixed"] | None = None  # for the reply text


class ActionCancelIn(BaseModel):
    conversation_id: ConversationId | None = None
    language: Literal["en", "te", "mixed"] | None = None


class ActionStateOut(BaseModel):
    state: ActionStateName
    draft_id: str | None = None
    token: str | None = None  # one-time confirmation token for this exact draft
    expires_at: str | None = None
    preview: dict[str, Any] | None = None
    missing: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    candidates: list[dict[str, Any]] = []
    code: str | None = None
    message: str | None = None
    record_id: str | None = None


class ActionResultOut(BaseModel):
    message: str
    action: ActionStateOut
