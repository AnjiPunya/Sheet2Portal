"""Turn a model's ``propose_action`` call into a stored draft -- never a change.

Everything is checked against the workbook's own schema and the existing
record services' rules (``validation.validate`` as a dry run, the same
workflow transitions, the same reference checks), so a draft that reaches
the user is one the record service would accept *right now*. Execution is a
separate step (``executor.py``) that re-checks all of it.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_session_token, new_session_token
from app.models.action_draft import ActionDraft
from app.models.record import Record
from app.models.user import User
from app.models.workbook import Workbook
from app.services.actions.amounts import parse_amount
from app.services.analysis.text import humanize
from app.services.auth.permissions import Permission, has_permission
from app.services.records import service
from app.services.records.field_rules import num
from app.services.records.links import norm
from app.services.records.schema import EntityRules, RecordContext
from app.services.records.validation import RecordValidationError, validate
from app.services.records.workflow import APPROVE, REJECT, RESUBMIT

CREATE, UPDATE, DELETE = "create", "update", "delete"
ACTIONS = (CREATE, UPDATE, DELETE, APPROVE, REJECT, RESUBMIT)
PERMISSION = {
    CREATE: Permission.CREATE_RECORD,
    UPDATE: Permission.EDIT_RECORD,
    DELETE: Permission.DELETE_RECORD,
    APPROVE: Permission.DECIDE,
    REJECT: Permission.DECIDE,
    RESUBMIT: Permission.EDIT_RECORD,
}
DRAFT_TTL = timedelta(minutes=10)
OPEN_STATUSES = ("pending", "incomplete")  # incomplete = waiting for clarification
_MAX_CANDIDATES = 5
_MAX_COMMENT = 1000


class PlanError(Exception):
    """Bad tool arguments (unknown worksheet/field): returned to the model so it retries."""


@dataclass
class PlanResult:
    """``state`` is clarification_required | awaiting_confirmation | failed."""

    state: str
    draft: ActionDraft | None = None
    token: str | None = None  # plaintext, only for the API response -- never shown to the model
    preview: dict | None = None
    missing: list[dict] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    candidates: list[dict] = field(default_factory=list)
    code: str | None = None
    message: str | None = None


def record_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def record_label(rules: EntityRules, data: dict) -> str:
    entity = rules.entity
    ident = data.get(entity.identifier_column) if entity.identifier_column else None
    title = data.get(entity.title_column) if entity.title_column else None
    parts = [str(p).strip() for p in (ident, title) if p not in (None, "") and str(p).strip()]
    unique = list(dict.fromkeys(parts))
    return " · ".join(unique) or humanize(entity.singular_label)


def _candidate(rules: EntityRules, record: Record) -> dict:
    status = rules.entity.status_column
    return {"record_id": str(record.id), "label": record_label(rules, record.data), "status": record.data.get(status) if status else None}


def resolve_record(rules: EntityRules, records: list[Record], ref: str | None) -> tuple[Record | None, list[dict]]:
    """Find one record from an id, identifier ("PR-1004") or name. Returns
    (record, []) on a confident match, else (None, candidates)."""
    text = norm(ref)
    if not text:
        return None, [_candidate(rules, r) for r in records[:_MAX_CANDIDATES]]
    for record in records:
        if str(record.id) == str(ref).strip():
            return record, []
    entity = rules.entity
    keys = [c for c in (entity.identifier_column, entity.title_column) if c]
    exact = [r for r in records if any(norm(r.data.get(k)) == text for k in keys) or norm(record_label(rules, r.data)) == text]
    if len(exact) == 1:
        return exact[0], []
    partial = exact or [r for r in records if any(text in norm(r.data.get(k)) for k in keys)]
    if len(partial) == 1:
        return partial[0], []
    return None, [_candidate(rules, r) for r in partial[:_MAX_CANDIDATES]]


def _field_label(rules: EntityRules, name: str) -> str:
    return humanize(name)


def _normalise_fields(rules: EntityRules, fields: dict | None) -> dict:
    """Map the model's field names onto real columns (case/spacing-insensitive)
    and convert spoken amounts for number columns. Unknown names -> PlanError."""
    if not fields:
        return {}
    if not isinstance(fields, dict):
        raise PlanError("'fields' must be an object of field name -> value")
    known = {norm(c.name): c.name for c in rules.entity.columns}
    known.update({norm(name): name for name in rules.extra_fields})
    out: dict = {}
    unknown: list[str] = []
    for raw_name, value in fields.items():
        name = known.get(norm(raw_name))
        if name is None:
            unknown.append(str(raw_name))
            continue
        column = rules.column(name)
        if column is None or column.inferred_type in ("int", "float"):
            value = parse_amount(value)
        out[name] = value
    if unknown:
        valid = ", ".join(c.name for c in rules.entity.columns)
        raise PlanError(f"Unknown field(s) {', '.join(unknown)} for '{rules.entity.worksheet}'. Valid fields: {valid}")
    return out


def _fmt(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


def stock_consequences(rules: EntityRules, before: dict | None, after: dict | None) -> list[str]:
    """What the record service's stock adjustment will do to linked inventory
    (a feed log uses feed), so the user hears it before confirming."""
    stock = getattr(getattr(rules, "fields", None), "linked_stock", None)
    column = (stock.stock or stock.outbound) if stock else None
    if stock is None or column is None:
        return []
    deltas: dict[str, float] = {}
    names: dict[str, object] = {}
    for data, sign in ((before, -1), (after, 1)):
        if not data:
            continue
        key = norm(data.get(stock.link.column))
        if key:
            deltas[key] = deltas.get(key, 0) + sign * (num(data.get(stock.quantity)) or 0)
            names[key] = data.get(stock.link.column)
    target = humanize(stock.link.target)
    out = []
    for key, used in deltas.items():
        if abs(used) < 1e-9:
            continue
        if stock.stock and used > 0:
            out.append(f"Reduces {target} {names[key]} {humanize(column)} by {_fmt(used)}.")
        elif stock.stock:
            out.append(f"Adds {_fmt(-used)} back to {target} {names[key]} {humanize(column)}.")
        else:
            change = "Adds" if used > 0 else "Removes"
            out.append(f"{change} {_fmt(abs(used))} to {target} {names[key]} {humanize(column)}.")
    return out


def _preview(
    action: str,
    rules: EntityRules,
    record: Record | None,
    data: dict | None,
    before: dict | None,
    status_change: tuple[str, str] | None = None,
    consequences: list[str] | None = None,
    comment: str | None = None,
) -> dict:
    computed = rules.computed
    fields: list[dict] = []
    if action == CREATE and data is not None:
        for name, value in data.items():
            if value in (None, ""):
                continue
            fields.append({"name": name, "label": _field_label(rules, name), "value": value, "computed": name in computed})
    elif action == UPDATE and data is not None and before is not None:
        for name in data:
            if data.get(name) != before.get(name):
                fields.append(
                    {"name": name, "label": _field_label(rules, name), "value": data.get(name), "previous": before.get(name), "computed": name in computed}
                )
    label = record_label(rules, data if action == CREATE and data else (record.data if record else {}))
    return {
        "action": action,
        "worksheet": rules.entity.worksheet,
        "entity_label": humanize(rules.entity.singular_label),
        "record_id": str(record.id) if record else None,
        "record_label": label,
        "fields": fields,
        "status_change": {"from": status_change[0], "to": status_change[1]} if status_change else None,
        "consequences": consequences or [],
        "comment": comment,
    }


def open_drafts(db: Session, user: User, workbook: Workbook, conversation_id: str) -> list[ActionDraft]:
    """This conversation's pending/incomplete drafts, newest first; expired ones are closed."""
    drafts = (
        db.query(ActionDraft)
        .filter(
            ActionDraft.user_id == user.id,
            ActionDraft.workbook_id == workbook.id,
            ActionDraft.conversation_id == conversation_id,
            ActionDraft.status.in_(OPEN_STATUSES),
        )
        .order_by(ActionDraft.created_at.desc())
        .all()
    )
    now = datetime.now(timezone.utc)
    live = []
    for draft in drafts:
        if aware(draft.expires_at) <= now:
            draft.status = "expired"
        else:
            live.append(draft)
    if len(live) != len(drafts):
        db.commit()
    return live


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class Planner:
    def __init__(self, db: Session, user: User, workbook: Workbook, ctx: RecordContext, records: dict[str, list[Record]], conversation_id: str):
        self.db = db
        self.user = user
        self.workbook = workbook
        self.ctx = ctx
        self.records = records
        self.conversation_id = conversation_id

    def editable_worksheets(self) -> list[EntityRules]:
        out = []
        for entity in self.ctx.config.entities:
            rules = self.ctx.rules(entity.worksheet)
            if rules is not None:
                out.append(rules)
        return out

    def _rules(self, worksheet: str | None) -> EntityRules:
        names = {norm(e.worksheet): e.worksheet for e in self.ctx.config.entities}
        name = names.get(norm(worksheet))
        rules = self.ctx.rules(name) if name else None
        if rules is None:
            valid = ", ".join(r.entity.worksheet for r in self.editable_worksheets())
            raise PlanError(f"Unknown or non-editable worksheet '{worksheet}'. Editable worksheets: {valid}")
        return rules

    def _store(self, status: str, action: str, rules: EntityRules, record: Record | None, payload: dict, preview: dict) -> tuple[ActionDraft, str]:
        for old in open_drafts(self.db, self.user, self.workbook, self.conversation_id):
            old.status = "superseded"
        token = new_session_token()
        draft = ActionDraft(
            tenant_id=self.workbook.tenant_id,
            workbook_id=self.workbook.id,
            user_id=self.user.id,
            conversation_id=self.conversation_id,
            action=action,
            worksheet=rules.entity.worksheet,
            record_id=record.id if record else None,
            payload=payload,
            preview=preview,
            record_hash=record_hash(record.data) if record else None,
            token_hash=hash_session_token(token),
            status=status,
            expires_at=datetime.now(timezone.utc) + DRAFT_TTL,
        )
        self.db.add(draft)
        self.db.commit()
        return draft, token

    def _base_fields(self, action: str, rules: EntityRules, record: Record | None) -> dict:
        """Fields from the draft being corrected (same action and target), so
        "make it 6 crore" only has to send what changed."""
        for draft in open_drafts(self.db, self.user, self.workbook, self.conversation_id):
            same_target = (draft.record_id == (record.id if record else None)) if action != CREATE else True
            if draft.action == action and draft.worksheet == rules.entity.worksheet and same_target:
                return dict(draft.payload.get("fields") or {})
        return {}

    def propose(self, args: dict) -> PlanResult:
        action = str(args.get("action") or "").strip().lower()
        if action not in ACTIONS:
            raise PlanError(f"'action' must be one of: {', '.join(ACTIONS)}")
        rules = self._rules(args.get("worksheet"))
        entity_label = humanize(rules.entity.singular_label).lower()

        if not has_permission(self.user.role, PERMISSION[action]):
            return PlanResult(state="failed", code="FORBIDDEN", message=f"You don't have permission to {action} {entity_label} records.")

        record: Record | None = None
        records = self.records.get(rules.entity.worksheet, [])
        if action != CREATE:
            record, candidates = resolve_record(rules, records, args.get("record"))
            if record is None:
                message = (
                    f"Several {humanize(rules.entity.label).lower()} match. Which one?"
                    if candidates
                    else f"I couldn't find that {entity_label}."
                )
                return self._clarify(action, rules, None, {}, candidates=candidates, message=message)

        fields = {**self._base_fields(action, rules, record), **_normalise_fields(rules, args.get("fields"))}
        comment = (str(args.get("comment") or "").strip() or None) if action in (APPROVE, REJECT, RESUBMIT) else None
        if comment and len(comment) > _MAX_COMMENT:
            comment = comment[:_MAX_COMMENT]

        workflow = rules.workflow
        if action in (CREATE, UPDATE):
            before = dict(record.data) if record else None
            if record is not None and workflow and workflow.is_final(record.data.get(workflow.status_column)):
                return PlanResult(state="failed", code="RECORD_LOCKED", message=f"This {entity_label} is {workflow.approved.lower()} and can't be edited.")
            others = [r.data for r in records if record is None or r.id != record.id]
            try:
                data = validate(self.ctx, rules, fields, before, others)
            except RecordValidationError as exc:
                return self._clarify(action, rules, record, fields, errors=exc.fields)
            if action == UPDATE and before is not None and data == before:
                return self._clarify(action, rules, record, fields, message="That wouldn't change anything. What should be different?")
            preview = _preview(action, rules, record, data, before, consequences=stock_consequences(rules, before, data))
            return self._ready(action, rules, record, {"fields": fields}, preview)

        if action == DELETE:
            if workflow and workflow.is_final(record.data.get(workflow.status_column)):
                return PlanResult(state="failed", code="RECORD_LOCKED", message=f"This {entity_label} is {workflow.approved.lower()} and can't be deleted.")
            in_use = service.references_to(self.ctx, rules.entity.worksheet, record.data)
            if in_use:
                listed = ", ".join(f"{n} {humanize(e).lower()}" for e, n in in_use.items())
                return PlanResult(state="failed", code="RECORD_IN_USE", message=f"Can't delete it: {listed} still refer to it.")
            consequences = [
                f"Permanently deletes {entity_label} {record_label(rules, record.data)}. This can't be undone.",
                *stock_consequences(rules, record.data, None),
            ]
            return self._ready(action, rules, record, {}, _preview(action, rules, record, None, None, consequences=consequences))

        # approve / reject / resubmit
        if workflow is None:
            return PlanResult(state="failed", code="NO_WORKFLOW", message=f"{humanize(rules.entity.label)} don't have an approval workflow.")
        current = record.data.get(workflow.status_column)
        new_status = workflow.next_status(current, action)
        if new_status is None:
            return PlanResult(
                state="failed", code="INVALID_TRANSITION", message=f"Can't {action} a {entity_label} that is {workflow.state(current).lower()}."
            )
        preview = _preview(action, rules, record, None, None, status_change=(workflow.state(current), new_status), comment=comment)
        return self._ready(action, rules, record, {"comment": comment}, preview)

    def _ready(self, action: str, rules: EntityRules, record: Record | None, payload: dict, preview: dict) -> PlanResult:
        draft, token = self._store("pending", action, rules, record, payload, preview)
        return PlanResult(state="awaiting_confirmation", draft=draft, token=token, preview=preview)

    def _clarify(
        self,
        action: str,
        rules: EntityRules,
        record: Record | None,
        fields: dict,
        errors: dict[str, str] | None = None,
        candidates: list[dict] | None = None,
        message: str | None = None,
    ) -> PlanResult:
        errors = dict(errors or {})
        missing = [
            {"name": name, "label": _field_label(rules, name), "message": msg}
            for name, msg in errors.items()
            if msg.endswith("is required.")
        ]
        invalid = {name: msg for name, msg in errors.items() if not msg.endswith("is required.")}
        # Keep what was collected so far, so the next answer only adds what's missing.
        preview = _preview(action, rules, record, dict(fields) if action == CREATE else None, None)
        draft, _ = self._store("incomplete", action, rules, record, {"fields": fields}, preview)
        return PlanResult(
            state="clarification_required",
            draft=draft,
            preview=preview,
            missing=missing,
            errors=invalid,
            candidates=candidates or [],
            message=message,
        )

    def cancel(self) -> bool:
        drafts = open_drafts(self.db, self.user, self.workbook, self.conversation_id)
        for draft in drafts:
            draft.status = "cancelled"
            draft.decided_at = datetime.now(timezone.utc)
        self.db.commit()
        return bool(drafts)
