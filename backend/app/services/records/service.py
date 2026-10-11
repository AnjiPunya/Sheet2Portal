"""Create / edit / delete records and make workflow decisions, with an
audit trail. Callers (routes) handle auth and tenant scoping first; this
module enforces the data and workflow rules."""

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.record import Record
from app.models.record_event import RecordEvent
from app.models.user import User
from app.models.workbook import Workbook
from app.models.worksheet import Worksheet
from app.services.analysis.text import humanize
from app.services.auth.permissions import Permission, has_permission
from app.services.parsing.jsonsafe import json_safe, json_safe_row
from app.services.records.field_rules import num
from app.services.records.links import norm
from app.services.records.schema import EntityRules, RecordContext
from app.services.records.validation import validate
from app.services.records.workflow import APPROVE, REJECT, RESUBMIT

_MAX_COMMENT = 1000
_DECISION_EVENT = {APPROVE: "approved", REJECT: "rejected", RESUBMIT: "resubmitted"}


class RecordError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _rules(ctx: RecordContext, worksheet: Worksheet) -> EntityRules:
    rules = ctx.rules(worksheet.name)
    if rules is None:
        raise RecordError(422, "NOT_EDITABLE", f"'{worksheet.name}' has no usable columns to edit.")
    return rules


def _other_rows(db: Session, worksheet: Worksheet, exclude: uuid.UUID | None) -> list[dict]:
    query = db.query(Record).filter(Record.worksheet_id == worksheet.id)
    if exclude is not None:
        query = query.filter(Record.id != exclude)
    return [r.data for r in query.all()]


def _sync_row_count(db: Session, worksheet: Worksheet) -> None:
    # Keeps the stored count true. This also stops the "missing records"
    # self-heal from re-importing the original file's rows after a user
    # deletes every record in a worksheet.
    worksheet.row_count = db.query(func.count(Record.id)).filter(Record.worksheet_id == worksheet.id).scalar()


def _diff(before: dict, after: dict) -> dict:
    keys = set(before) | set(after)
    return {k: [before.get(k), after.get(k)] for k in sorted(keys) if before.get(k) != after.get(k)}


def _log(
    db: Session,
    workbook: Workbook,
    worksheet: Worksheet,
    record_id: uuid.UUID,
    user: User,
    action: str,
    changes: dict,
    from_status: str | None = None,
    to_status: str | None = None,
    comment: str | None = None,
) -> None:
    db.add(
        RecordEvent(
            tenant_id=workbook.tenant_id,
            workbook_id=workbook.id,
            worksheet=worksheet.name,
            record_id=record_id,
            user_id=user.id,
            user_name=user.display_name or user.email,
            action=action,
            from_status=from_status,
            to_status=to_status,
            comment=comment,
            changes={field: [json_safe(old), json_safe(new)] for field, (old, new) in changes.items()},
        )
    )


def _record_label(rules: EntityRules, data: dict) -> str:
    entity = rules.entity
    for column in (entity.identifier_column, entity.title_column):
        if column and data.get(column) not in (None, ""):
            return str(data[column])
    return humanize(entity.singular_label).lower()


def _adjust_stock(
    db: Session,
    ctx: RecordContext,
    workbook: Workbook,
    rules: EntityRules,
    before: dict | None,
    after: dict | None,
    user: User,
) -> None:
    """Keep the linked inventory in step with consumption records (a feed log
    uses feed): take the used quantity off the item's stock on create, put it
    back on delete, and move the difference on edit. Logged on the inventory
    record so every stock change is traceable."""
    stock = rules.fields.linked_stock
    if stock is None:
        return
    deltas: dict[str, float] = {}
    for data, sign in ((before, -1), (after, 1)):
        if not data:
            continue
        key = norm(data.get(stock.link.column))
        quantity = num(data.get(stock.quantity)) or 0
        if key:
            deltas[key] = deltas.get(key, 0) + sign * quantity
    target_sheet = next((w for w in workbook.worksheets if w.name == stock.link.target), None)
    if target_sheet is None:
        return
    source = after or before or {}
    for key, used in deltas.items():
        if abs(used) < 1e-9:
            continue
        target = next(
            (r for r in db.query(Record).filter(Record.worksheet_id == target_sheet.id).all() if norm(r.data.get(stock.link.target_column)) == key),
            None,
        )
        if target is None:
            continue
        data = dict(target.data)
        column = stock.stock or stock.outbound
        if column is None:
            continue
        current = num(data.get(column)) or 0
        updated = current - used if stock.stock else current + used
        data[column] = int(updated) if float(updated).is_integer() and not isinstance(data.get(column), float) else round(updated, 4)
        changes = _diff(target.data, data)
        target.data = json_safe_row(data)
        _log(
            db,
            workbook,
            target_sheet,
            target.id,
            user,
            "updated",
            changes,
            comment=f"Stock adjusted by {humanize(rules.entity.singular_label).lower()} {_record_label(rules, source)}",
        )


def _ensure_not_final(rules: EntityRules, record: Record, verb: str) -> None:
    workflow = rules.workflow
    if workflow and workflow.is_final(record.data.get(workflow.status_column)):
        raise RecordError(409, "RECORD_LOCKED", f"This {humanize(rules.entity.singular_label).lower()} is {workflow.approved.lower()} and can't be {verb}.")


def create_record(db: Session, ctx: RecordContext, workbook: Workbook, worksheet: Worksheet, payload: dict, user: User) -> Record:
    rules = _rules(ctx, worksheet)
    data = validate(ctx, rules, payload, None, _other_rows(db, worksheet, None))
    next_index = (db.query(func.max(Record.row_index)).filter(Record.worksheet_id == worksheet.id).scalar() or -1) + 1
    record = Record(worksheet_id=worksheet.id, row_index=next_index, data=json_safe_row(data))
    db.add(record)
    db.flush()
    _sync_row_count(db, worksheet)
    _adjust_stock(db, ctx, workbook, rules, None, record.data, user)
    status = rules.entity.status_column
    _log(db, workbook, worksheet, record.id, user, "created", _diff({}, record.data), to_status=record.data.get(status) if status else None)
    db.commit()
    db.refresh(record)
    return record


def update_record(
    db: Session, ctx: RecordContext, workbook: Workbook, worksheet: Worksheet, record: Record, payload: dict, user: User
) -> Record:
    rules = _rules(ctx, worksheet)
    _ensure_not_final(rules, record, "edited")
    before = dict(record.data)
    data = json_safe_row(validate(ctx, rules, payload, before, _other_rows(db, worksheet, record.id)))
    changes = _diff(before, data)
    if changes:
        record.data = data  # reassign: JSON columns don't track in-place mutation
        _adjust_stock(db, ctx, workbook, rules, before, data, user)
        _log(db, workbook, worksheet, record.id, user, "updated", changes)
        db.commit()
        db.refresh(record)
    return record


def references_to(ctx: RecordContext, worksheet: str, data: dict) -> dict[str, int]:
    """How many records in other worksheets point at this one."""
    counts: dict[str, int] = {}
    for link in ctx.links:
        if link.target != worksheet:
            continue
        key = norm(data.get(link.target_column))
        if not key:
            continue
        count = sum(norm(row.get(link.column)) == key for row in ctx.rows_by_entity.get(link.entity, []))
        if count:
            counts[link.entity] = counts.get(link.entity, 0) + count
    return counts


def delete_record(db: Session, ctx: RecordContext, workbook: Workbook, worksheet: Worksheet, record: Record, user: User) -> None:
    rules = _rules(ctx, worksheet)
    _ensure_not_final(rules, record, "deleted")
    in_use = references_to(ctx, worksheet.name, record.data)
    if in_use:
        listed = ", ".join(f"{n} {humanize(entity).lower()}" for entity, n in in_use.items())
        raise RecordError(409, "RECORD_IN_USE", f"Can't delete: {listed} still refer to this record. Reassign or delete those first.")
    _log(db, workbook, worksheet, record.id, user, "deleted", _diff(record.data, {}))
    _adjust_stock(db, ctx, workbook, rules, record.data, None, user)
    db.delete(record)
    db.flush()
    _sync_row_count(db, worksheet)
    db.commit()


def decide(
    db: Session,
    ctx: RecordContext,
    workbook: Workbook,
    worksheet: Worksheet,
    record: Record,
    action: str,
    comment: str | None,
    user: User,
) -> Record:
    rules = _rules(ctx, worksheet)
    workflow = rules.workflow
    if workflow is None:
        raise RecordError(422, "NO_WORKFLOW", f"{humanize(rules.entity.label)} don't have an approval workflow.")
    if action not in _DECISION_EVENT:
        raise RecordError(422, "INVALID_ACTION", "Action must be approve, reject or resubmit.")
    needed = Permission.EDIT_RECORD if action == RESUBMIT else Permission.DECIDE
    if not has_permission(user.role, needed):
        raise RecordError(403, "FORBIDDEN", "You don't have permission to do that.")
    comment = (comment or "").strip() or None
    if comment and len(comment) > _MAX_COMMENT:
        raise RecordError(422, "COMMENT_TOO_LONG", f"Keep comments under {_MAX_COMMENT} characters.")

    current = record.data.get(workflow.status_column)
    new_status = workflow.next_status(current, action)
    if new_status is None:
        raise RecordError(
            409,
            "INVALID_TRANSITION",
            f"Can't {action} a {humanize(rules.entity.singular_label).lower()} that is {workflow.state(current).lower()}.",
        )
    data = dict(record.data)
    data[workflow.status_column] = new_status
    record.data = data
    _log(
        db,
        workbook,
        worksheet,
        record.id,
        user,
        _DECISION_EVENT[action],
        {workflow.status_column: [current, new_status]},
        from_status=current,
        to_status=new_status,
        comment=comment,
    )
    db.commit()
    db.refresh(record)
    return record


def record_actions(rules: EntityRules | None, data: dict, user: User) -> dict[str, bool]:
    """What the current user may do with this record right now. Used by the
    UI to show only permitted buttons; each action is re-checked on the server."""
    can = lambda p: has_permission(user.role, p)  # noqa: E731
    if rules is None:
        return {"edit": False, "delete": False, "approve": False, "reject": False, "resubmit": False}
    workflow = rules.workflow
    final = bool(workflow and workflow.is_final(data.get(workflow.status_column)))
    state = workflow.state(data.get(workflow.status_column)) if workflow else None
    return {
        "edit": can(Permission.EDIT_RECORD) and not final,
        "delete": can(Permission.DELETE_RECORD) and not final,
        "approve": bool(workflow) and can(Permission.DECIDE) and state == (workflow.pending if workflow else None),
        "reject": bool(workflow) and can(Permission.DECIDE) and state == (workflow.pending if workflow else None),
        "resubmit": bool(workflow) and can(Permission.EDIT_RECORD) and state == (workflow.rejected if workflow else None),
    }


def history(db: Session, workbook: Workbook, record_id: uuid.UUID) -> list[RecordEvent]:
    return (
        db.query(RecordEvent)
        .filter(RecordEvent.workbook_id == workbook.id, RecordEvent.record_id == record_id)
        .order_by(RecordEvent.created_at.desc())
        .all()
    )
