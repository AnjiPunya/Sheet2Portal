import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_tenant_id
from app.api.routes.workbooks import storage
from app.core.db import get_db
from app.models.record import Record
from app.models.workbook import Workbook
from app.models.worksheet import Worksheet
from app.schemas.portal import PortalConfigOut, RecordOut, RecordPageOut
from app.services.analysis.backfill import backfill_missing_records
from app.services.analysis.engine import build_portal_config
from app.services.analysis.loader import load_sheet_data
from app.services.analysis.types import PortalConfig

router = APIRouter(prefix="/api/workbooks", tags=["portal"])


def _error(status_code: int, error_code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error_code": error_code, "message": message})


def _load_workbook_for_portal(db: Session, workbook_id: uuid.UUID, tenant_id: uuid.UUID) -> Workbook:
    workbook = (
        db.query(Workbook)
        .options(selectinload(Workbook.worksheets).selectinload(Worksheet.columns))
        .filter(Workbook.id == workbook_id, Workbook.tenant_id == tenant_id)
        .first()
    )
    if workbook is None:
        raise _error(404, "NOT_FOUND", "Workbook not found")
    return workbook


def _build_config(db: Session, workbook: Workbook) -> PortalConfig:
    backfill_missing_records(db, workbook, storage)
    sheets = load_sheet_data(db, workbook)
    title = workbook.original_filename.rsplit(".", 1)[0]
    return build_portal_config(title, sheets)


@router.get("/{workbook_id}/portal", response_model=PortalConfigOut)
def get_portal_config(
    workbook_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
) -> PortalConfig:
    workbook = _load_workbook_for_portal(db, workbook_id, tenant_id)
    if workbook.status != "ready":
        raise _error(409, "WORKBOOK_NOT_READY", f"Workbook status is '{workbook.status}', not ready")
    config = _build_config(db, workbook)
    if not config.entities:
        raise _error(
            422,
            "NO_USABLE_WORKSHEETS",
            "No worksheet in this workbook produced usable data for a portal. "
            "The original file may be empty, unreadable, or every sheet lacks data rows. "
            "Try re-uploading the file.",
        )
    return config


def _get_worksheet(workbook: Workbook, worksheet_name: str) -> Worksheet:
    worksheet = next((w for w in workbook.worksheets if w.name == worksheet_name), None)
    if worksheet is None:
        raise _error(404, "NOT_FOUND", f"Worksheet '{worksheet_name}' not found in this workbook")
    return worksheet


@router.get("/{workbook_id}/worksheets/{worksheet_name}/records", response_model=RecordPageOut)
def list_records(
    workbook_id: uuid.UUID,
    worksheet_name: str,
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
) -> RecordPageOut:
    workbook = _load_workbook_for_portal(db, workbook_id, tenant_id)
    worksheet = _get_worksheet(workbook, worksheet_name)
    config = _build_config(db, workbook)
    entity = next((e for e in config.entities if e.worksheet == worksheet_name), None)

    records = db.query(Record).filter(Record.worksheet_id == worksheet.id).order_by(Record.row_index).all()

    if status and entity and entity.status_column:
        records = [r for r in records if str(r.data.get(entity.status_column, "")).strip() == status]

    if search:
        needle = search.strip().lower()
        searchable_columns = (
            [c.name for c in entity.columns if c.inferred_type == "string"] if entity else []
        )
        records = [
            r
            for r in records
            if any(needle in str(r.data.get(col, "")).lower() for col in searchable_columns)
        ]

    total = len(records)
    start = (page - 1) * page_size
    page_records = records[start : start + page_size]

    return RecordPageOut(
        records=[RecordOut(id=str(r.id), data=r.data) for r in page_records],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{workbook_id}/worksheets/{worksheet_name}/records/{record_id}")
def get_record_detail(
    workbook_id: uuid.UUID,
    worksheet_name: str,
    record_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
) -> dict:
    workbook = _load_workbook_for_portal(db, workbook_id, tenant_id)
    worksheet = _get_worksheet(workbook, worksheet_name)
    record = (
        db.query(Record).filter(Record.id == record_id, Record.worksheet_id == worksheet.id).first()
    )
    if record is None:
        raise _error(404, "NOT_FOUND", "Record not found")

    config = _build_config(db, workbook)
    all_records_by_entity: dict[str, list[Record]] = {
        e.worksheet: db.query(Record)
        .join(Worksheet, Record.worksheet_id == Worksheet.id)
        .filter(Worksheet.workbook_id == workbook.id, Worksheet.name == e.worksheet)
        .all()
        for e in config.entities
    }

    related: list[dict] = []

    # Outgoing: this record references another entity (e.g. Tasks.Project -> Projects).
    for rel in config.relationships:
        if rel.from_entity != worksheet_name:
            continue
        value = record.data.get(rel.from_column)
        if value is None or str(value).strip() == "":
            continue
        matches = [
            r
            for r in all_records_by_entity.get(rel.to_entity, [])
            if str(r.data.get(rel.to_column, "")).strip().lower() == str(value).strip().lower()
        ]
        if matches:
            related.append(
                {
                    "entity": rel.to_entity,
                    "relationship": f"{rel.from_column} -> {rel.to_entity}",
                    "records": [{"id": str(m.id), "data": m.data} for m in matches],
                }
            )

    # Incoming: other entities have a column that references this record.
    entity = next((e for e in config.entities if e.worksheet == worksheet_name), None)
    identity_columns = {c for c in (entity.identifier_column, entity.title_column) if c} if entity else set()
    for rel in config.relationships:
        if rel.to_entity != worksheet_name or rel.to_column not in identity_columns:
            continue
        own_value = record.data.get(rel.to_column)
        if own_value is None:
            continue
        matches = [
            r
            for r in all_records_by_entity.get(rel.from_entity, [])
            if str(r.data.get(rel.from_column, "")).strip().lower() == str(own_value).strip().lower()
        ]
        if matches:
            related.append(
                {
                    "entity": rel.from_entity,
                    "relationship": f"{rel.from_entity}.{rel.from_column}",
                    "records": [{"id": str(m.id), "data": m.data} for m in matches],
                }
            )

    return {"id": str(record.id), "data": record.data, "related": related}
