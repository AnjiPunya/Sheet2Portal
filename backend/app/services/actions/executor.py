"""Execute a confirmed draft through the existing record services.

Called only from an explicit confirmation (a Confirm click, or a plain
"yes" classified deterministically) carrying the draft's one-time token.
Everything is re-checked at execution time: owner, conversation, token,
expiry, tenant, permission, whether the target record changed since the
draft was shown, and then the record service's own validation and workflow
rules. A draft is claimed atomically (pending -> executing), so a replayed
or double-submitted confirmation can't run it twice.
"""

import hmac
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes.portal import _get_worksheet, _load_portal, _load_workbook_for_portal
from app.core.security import hash_session_token
from app.models.action_draft import ActionDraft
from app.models.record import Record
from app.models.user import User
from app.services.actions.planner import CREATE, DELETE, PERMISSION, UPDATE, aware, record_hash, record_label
from app.services.auth.permissions import has_permission
from app.services.records import service
from app.services.records.schema import build_context
from app.services.records.validation import RecordValidationError

_GONE = {
    "completed": ("ALREADY_EXECUTED", "This action was already completed."),
    "executing": ("ALREADY_EXECUTED", "This action is already being carried out."),
    "failed": ("ALREADY_USED", "This draft already failed. Ask me again to prepare a new one."),
    "cancelled": ("DRAFT_CANCELLED", "This draft was cancelled."),
    "superseded": ("DRAFT_SUPERSEDED", "This draft was replaced by a newer one. Please review the latest draft."),
    "expired": ("DRAFT_EXPIRED", "This draft expired. Ask me again to prepare it."),
    "incomplete": ("DRAFT_INCOMPLETE", "This draft still needs more details before it can be confirmed."),
}


@dataclass
class Outcome:
    """``state`` is completed | failed | cancelled."""

    state: str
    draft: ActionDraft | None
    code: str | None = None
    message: str = ""
    record_id: str | None = None
    record_label: str | None = None
    fields: dict[str, str] = field(default_factory=dict)


def _fail(draft: ActionDraft | None, code: str, message: str, fields: dict | None = None) -> Outcome:
    return Outcome(state="failed", draft=draft, code=code, message=message, fields=fields or {})


def _load_owned(db: Session, user: User, draft_id: str | uuid.UUID) -> ActionDraft | None:
    try:
        key = draft_id if isinstance(draft_id, uuid.UUID) else uuid.UUID(str(draft_id))
    except ValueError:
        return None
    draft = db.get(ActionDraft, key)
    # Another user's draft looks exactly like a missing one.
    if draft is None or draft.user_id != user.id or draft.tenant_id != user.tenant_id:
        return None
    return draft


def _check(db: Session, user: User, draft_id, token: str | None, conversation_id: str | None, workbook_id) -> tuple[ActionDraft | None, Outcome | None]:
    draft = _load_owned(db, user, draft_id)
    if draft is None:
        return None, _fail(None, "DRAFT_NOT_FOUND", "I couldn't find that draft.")
    if workbook_id is not None and str(draft.workbook_id) != str(workbook_id):
        return None, _fail(None, "DRAFT_NOT_FOUND", "I couldn't find that draft.")
    if conversation_id is not None and draft.conversation_id != conversation_id:
        return draft, _fail(draft, "DRAFT_MISMATCH", "That draft belongs to a different conversation.")
    if not token or not hmac.compare_digest(draft.token_hash, hash_session_token(token)):
        return draft, _fail(draft, "INVALID_CONFIRMATION", "That confirmation doesn't match the current draft.")
    if draft.status == "pending" and aware(draft.expires_at) <= datetime.now(timezone.utc):
        draft.status = "expired"
        db.commit()
    if draft.status != "pending":
        code, message = _GONE.get(draft.status, ("ALREADY_USED", "This draft can't be confirmed."))
        return draft, _fail(draft, code, message)
    return draft, None


def _finish(db: Session, draft: ActionDraft, outcome: Outcome) -> Outcome:
    draft.status = "completed" if outcome.state == "completed" else "failed"
    draft.decided_at = datetime.now(timezone.utc)
    draft.result = {"code": outcome.code, "message": outcome.message, "record_id": outcome.record_id, "fields": outcome.fields}
    db.commit()
    return outcome


def execute(
    db: Session,
    user: User,
    draft_id,
    token: str | None,
    conversation_id: str | None = None,
    workbook_id=None,
) -> Outcome:
    draft, problem = _check(db, user, draft_id, token, conversation_id, workbook_id)
    if problem:
        return problem

    # Atomic claim: only one confirmation can move this draft out of pending.
    claimed = (
        db.query(ActionDraft)
        .filter(ActionDraft.id == draft.id, ActionDraft.status == "pending")
        .update({ActionDraft.status: "executing"}, synchronize_session=False)
    )
    db.commit()
    if claimed != 1:
        return _fail(draft, "ALREADY_EXECUTED", "This action was already completed.")
    db.refresh(draft)

    try:
        outcome = _run(db, user, draft)
    except RecordValidationError as exc:
        db.rollback()
        outcome = _fail(draft, "VALIDATION_FAILED", "Some details are no longer valid: " + "; ".join(f"{k}: {v}" for k, v in exc.fields.items()), exc.fields)
    except service.RecordError as exc:
        db.rollback()
        outcome = _fail(draft, exc.code, exc.message)
    except HTTPException as exc:
        db.rollback()
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        outcome = _fail(draft, detail.get("error_code", "FAILED"), detail.get("message", "The action could not be completed."))
    draft = db.get(ActionDraft, draft.id)
    outcome.draft = draft
    return _finish(db, draft, outcome)


def _run(db: Session, user: User, draft: ActionDraft) -> Outcome:
    if not has_permission(user.role, PERMISSION[draft.action]):
        return _fail(draft, "FORBIDDEN", "You don't have permission to do that.")
    workbook = _load_workbook_for_portal(db, draft.workbook_id, user.tenant_id)
    if workbook.status != "ready":
        return _fail(draft, "WORKBOOK_NOT_READY", "The workbook isn't ready.")
    worksheet = _get_worksheet(workbook, draft.worksheet)
    config, sheets = _load_portal(db, workbook)
    ctx = build_context(config, {s.name: s.rows for s in sheets})
    rules = ctx.rules(worksheet.name)
    if rules is None:
        return _fail(draft, "NOT_EDITABLE", f"'{worksheet.name}' can't be edited.")

    record: Record | None = None
    if draft.action != CREATE:
        record = db.query(Record).filter(Record.id == draft.record_id, Record.worksheet_id == worksheet.id).first()
        if record is None:
            return _fail(draft, "RECORD_NOT_FOUND", "That record no longer exists.")
        if record_hash(record.data) != draft.record_hash:
            return _fail(draft, "STALE_DRAFT", "The record was changed after this draft was prepared. Please review it again.")
        label = record_label(rules, record.data)

    fields = dict(draft.payload.get("fields") or {})
    if draft.action == CREATE:
        record = service.create_record(db, ctx, workbook, worksheet, fields, user)
        label = record_label(rules, record.data)
    elif draft.action == UPDATE:
        record = service.update_record(db, ctx, workbook, worksheet, record, fields, user)
        label = record_label(rules, record.data)
    elif draft.action == DELETE:
        record_id = str(record.id)
        service.delete_record(db, ctx, workbook, worksheet, record, user)
        return Outcome(state="completed", draft=draft, record_id=record_id, record_label=label)
    else:
        record = service.decide(db, ctx, workbook, worksheet, record, draft.action, draft.payload.get("comment"), user)
    return Outcome(state="completed", draft=draft, record_id=str(record.id), record_label=label)


def cancel(db: Session, user: User, draft_id, conversation_id: str | None = None, workbook_id=None) -> Outcome:
    draft = _load_owned(db, user, draft_id)
    if draft is None or (workbook_id is not None and str(draft.workbook_id) != str(workbook_id)):
        return _fail(None, "DRAFT_NOT_FOUND", "I couldn't find that draft.")
    if conversation_id is not None and draft.conversation_id != conversation_id:
        return _fail(draft, "DRAFT_MISMATCH", "That draft belongs to a different conversation.")
    if draft.status not in ("pending", "incomplete"):
        code, message = _GONE.get(draft.status, ("ALREADY_USED", "This draft can't be cancelled."))
        return _fail(draft, code, message)
    draft.status = "cancelled"
    draft.decided_at = datetime.now(timezone.utc)
    db.commit()
    return Outcome(state="cancelled", draft=draft)
