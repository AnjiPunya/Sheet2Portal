"""Create / edit / delete records, approval decisions, and record activity.

Every route: signed-in user (session cookie) -> workbook must belong to the
user's tenant (404 otherwise) -> permission check -> data/workflow rules in
app/services/records. Nothing here is specific to any business domain.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.api.routes.portal import _error, _get_worksheet, _load_portal, _load_workbook_for_portal
from app.core.db import get_db
from app.models.record import Record
from app.models.user import User
from app.models.workbook import Workbook
from app.models.worksheet import Worksheet
from app.schemas.records import DecisionIn, RecordActivityOut, RecordEventOut, RecordWriteIn, RecordWriteOut
from app.services.auth.permissions import Permission, has_permission
from app.services.records import service
from app.services.records.schema import RecordContext, build_context, form_schema
from app.services.records.validation import RecordValidationError

router = APIRouter(prefix="/api/workbooks", tags=["records"])


def _load(db: Session, workbook_id: uuid.UUID, user: User, worksheet_name: str) -> tuple[Workbook, Worksheet, RecordContext]:
    workbook = _load_workbook_for_portal(db, workbook_id, user.tenant_id)
    if workbook.status != "ready":
        raise _error(409, "WORKBOOK_NOT_READY", f"Workbook status is '{workbook.status}', not ready")
    worksheet = _get_worksheet(workbook, worksheet_name)
    config, sheets = _load_portal(db, workbook)
    return workbook, worksheet, build_context(config, {s.name: s.rows for s in sheets})


def _record(db: Session, worksheet: Worksheet, record_id: uuid.UUID) -> Record:
    record = db.query(Record).filter(Record.id == record_id, Record.worksheet_id == worksheet.id).first()
    if record is None:
        raise _error(404, "NOT_FOUND", "Record not found")
    return record


def _run(fn, *args):
    """Map service-level errors onto HTTP responses."""
    try:
        return fn(*args)
    except RecordValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "VALIDATION_FAILED", "message": str(exc), "fields": exc.fields},
        ) from exc
    except service.RecordError as exc:
        raise _error(exc.status, exc.code, exc.message) from exc


def _out(ctx: RecordContext, worksheet: Worksheet, record: Record, user: User) -> RecordWriteOut:
    actions = service.record_actions(ctx.rules(worksheet.name), record.data, user)
    return RecordWriteOut(id=str(record.id), data=record.data, actions=actions)


@router.get("/{workbook_id}/worksheets/{worksheet_name}/schema")
def get_form_schema(
    workbook_id: uuid.UUID,
    worksheet_name: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _, worksheet, ctx = _load(db, workbook_id, user, worksheet_name)
    rules = ctx.rules(worksheet.name)
    if rules is None:
        raise _error(422, "NOT_EDITABLE", f"'{worksheet.name}' has no usable columns to edit.")
    schema = form_schema(ctx, rules)
    schema["can_create"] = has_permission(user.role, Permission.CREATE_RECORD)
    return schema


@router.post(
    "/{workbook_id}/worksheets/{worksheet_name}/records",
    response_model=RecordWriteOut,
    status_code=201,
)
def create_record(
    workbook_id: uuid.UUID,
    worksheet_name: str,
    payload: RecordWriteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.CREATE_RECORD)),
) -> RecordWriteOut:
    workbook, worksheet, ctx = _load(db, workbook_id, user, worksheet_name)
    record = _run(service.create_record, db, ctx, workbook, worksheet, payload.data, user)
    return _out(ctx, worksheet, record, user)


@router.patch("/{workbook_id}/worksheets/{worksheet_name}/records/{record_id}", response_model=RecordWriteOut)
def update_record(
    workbook_id: uuid.UUID,
    worksheet_name: str,
    record_id: uuid.UUID,
    payload: RecordWriteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.EDIT_RECORD)),
) -> RecordWriteOut:
    workbook, worksheet, ctx = _load(db, workbook_id, user, worksheet_name)
    record = _record(db, worksheet, record_id)
    record = _run(service.update_record, db, ctx, workbook, worksheet, record, payload.data, user)
    return _out(ctx, worksheet, record, user)


@router.delete("/{workbook_id}/worksheets/{worksheet_name}/records/{record_id}", status_code=204)
def delete_record(
    workbook_id: uuid.UUID,
    worksheet_name: str,
    record_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.DELETE_RECORD)),
) -> None:
    workbook, worksheet, ctx = _load(db, workbook_id, user, worksheet_name)
    record = _record(db, worksheet, record_id)
    _run(service.delete_record, db, ctx, workbook, worksheet, record, user)


@router.post("/{workbook_id}/worksheets/{worksheet_name}/records/{record_id}/decision", response_model=RecordWriteOut)
def decide(
    workbook_id: uuid.UUID,
    worksheet_name: str,
    record_id: uuid.UUID,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RecordWriteOut:
    """Approve / reject / resubmit. The permission depends on the action, so
    it's checked in the service rather than by a route dependency."""
    workbook, worksheet, ctx = _load(db, workbook_id, user, worksheet_name)
    record = _record(db, worksheet, record_id)
    record = _run(service.decide, db, ctx, workbook, worksheet, record, payload.action, payload.comment, user)
    return _out(ctx, worksheet, record, user)


@router.get("/{workbook_id}/worksheets/{worksheet_name}/records/{record_id}/activity", response_model=RecordActivityOut)
def record_activity(
    workbook_id: uuid.UUID,
    worksheet_name: str,
    record_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RecordActivityOut:
    workbook, worksheet, ctx = _load(db, workbook_id, user, worksheet_name)
    record = _record(db, worksheet, record_id)
    events = service.history(db, workbook, record.id)
    return RecordActivityOut(
        actions=service.record_actions(ctx.rules(worksheet.name), record.data, user),
        history=[
            RecordEventOut(
                id=str(e.id),
                action=e.action,
                user_name=e.user_name,
                from_status=e.from_status,
                to_status=e.to_status,
                comment=e.comment,
                changes=e.changes,
                created_at=e.created_at,
            )
            for e in events
        ],
    )
