import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_tenant_id, get_current_user
from app.api.routes.portal import _build_config, _error, _load_workbook_for_portal
from app.core.config import settings
from app.core.db import get_db
from app.models.record import Record
from app.models.user import User
from app.models.worksheet import Worksheet
from app.schemas.actions import ActionStateOut
from app.schemas.chat import ChatRequest, ChatResponseOut, ChatSuggestionsOut
from app.services.actions.session import ActionSession, PendingRef
from app.services.ai.base import (
    ChatMessage,
    ProviderError,
    ProviderNotConfigured,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.services.ai.orchestrator import extract_references, run_chat_turn
from app.services.ai.providers import fallback_providers
from app.services.ai.registry import get_provider
from app.services.ai.suggestions import generate_suggestions
from app.services.ai.tools import ChatContext

router = APIRouter(prefix="/api/workbooks", tags=["chat"])


def _load_chat_context(db: Session, workbook) -> ChatContext:
    config = _build_config(db, workbook)
    records_by_entity = {
        entity.worksheet: db.query(Record)
        .join(Worksheet, Record.worksheet_id == Worksheet.id)
        .filter(Worksheet.workbook_id == workbook.id, Worksheet.name == entity.worksheet)
        .all()
        for entity in config.entities
    }
    return ChatContext(config=config, records_by_entity=records_by_entity)


def _ensure_ready(workbook) -> None:
    if workbook.status != "ready":
        raise _error(409, "WORKBOOK_NOT_READY", f"Workbook status is '{workbook.status}', not ready")


@router.post("/{workbook_id}/chat", response_model=ChatResponseOut)
async def chat(
    workbook_id: uuid.UUID,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatResponseOut:
    workbook = _load_workbook_for_portal(db, workbook_id, user.tenant_id)
    _ensure_ready(workbook)

    ctx = _load_chat_context(db, workbook)
    if not ctx.config.entities:
        raise _error(422, "NO_USABLE_WORKSHEETS", "This workbook has no usable data for the chatbot to query.")

    # Business actions: a plain yes/no to the draft the client shows is
    # handled deterministically, without calling the model.
    pending = PendingRef(payload.pending_action.draft_id, payload.pending_action.token) if payload.pending_action else None
    actions = ActionSession(db, user, workbook, ctx, payload.conversation_id, pending)
    if payload.messages[-1].role == "user":
        reply = actions.resolve_utterance(payload.messages[-1].content)
        if reply is not None:
            return ChatResponseOut(message=reply, references=[], tool_calls=[], provider="actions", action=ActionStateOut(**actions.state))

    try:
        provider = get_provider(settings, requested=payload.provider)
    except ProviderNotConfigured as exc:
        raise _error(503, "CHATBOT_NOT_CONFIGURED", str(exc)) from exc

    history = [ChatMessage(role=m.role, content=m.content) for m in payload.messages]
    history = history[-settings.chat_max_history_messages :]

    # If the provider is rate limited or down (after a multi-key provider
    # like Gemini has already tried each of its keys), retry the whole turn
    # on the other configured providers in routing order.
    candidates = [provider, *fallback_providers(settings, provider.name)]
    try:
        for index, provider in enumerate(candidates):
            try:
                result, tool_log = await run_chat_turn(
                    provider,
                    history,
                    ctx,
                    max_iterations=settings.chat_max_tool_iterations,
                    max_page_size=settings.chat_tool_max_page_size,
                    extra_tools=actions.tools(),
                    system_suffix=actions.system_suffix(),
                )
                break
            except (ProviderRateLimited, ProviderUnavailable):
                if index == len(candidates) - 1:
                    raise
    except ProviderRateLimited as exc:
        raise _error(429, "PROVIDER_RATE_LIMITED", f"{provider.name} rate limit reached. Try again shortly.") from exc
    except ProviderTimeout as exc:
        raise _error(504, "PROVIDER_TIMEOUT", f"{provider.name} did not respond in time.") from exc
    except ProviderUnavailable as exc:
        raise _error(502, "PROVIDER_UNAVAILABLE", f"{provider.name} is temporarily unavailable.") from exc
    except ProviderError as exc:
        raise _error(502, "PROVIDER_ERROR", str(exc)) from exc

    return ChatResponseOut(
        message=result.message.content or "I wasn't able to generate a response. Please try rephrasing your question.",
        references=extract_references(tool_log, ctx=ctx),
        tool_calls=[{"name": entry["name"], "arguments": entry["arguments"]} for entry in tool_log],
        provider=provider.name,
        action=ActionStateOut(**actions.state) if actions.state else None,
    )


@router.get("/{workbook_id}/chat/suggestions", response_model=ChatSuggestionsOut)
def chat_suggestions(
    workbook_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
) -> ChatSuggestionsOut:
    workbook = _load_workbook_for_portal(db, workbook_id, tenant_id)
    if workbook.status != "ready":
        return ChatSuggestionsOut(suggestions=[])
    config = _build_config(db, workbook)
    return ChatSuggestionsOut(suggestions=generate_suggestions(config))
