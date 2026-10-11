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
from app.services.analysis.relationships import related_rows_for
from app.services.analysis.title import generate_portal_title
from app.services.analysis.types import IdentifiedRow, PortalConfig

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
    title = workbook.display_title or generate_portal_title(workbook.original_filename)
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


def _filter_related(
    db: Session,
    workbook: Workbook,
    config: PortalConfig,
    worksheet_name: str,
    records: list[Record],
    related_worksheet: str | None,
    related_record_id: uuid.UUID | None,
) -> list[Record]:
    """Keep only ``records`` related to one parent record (the record-detail
    "View all" link), using the same detected relationships and matching as
    the record-detail endpoint -- never a client-supplied column."""
    if not related_worksheet or related_record_id is None:
        raise _error(422, "INVALID_RELATED_FILTER", "related_worksheet and related_record_id must be given together")

    linked = any(
        {rel.from_entity, rel.to_entity} == {worksheet_name, related_worksheet} for rel in config.relationships
    )
    if not linked:
        raise _error(
            422,
            "NO_RELATIONSHIP",
            f"No detected relationship between '{related_worksheet}' and '{worksheet_name}'",
        )

    # Scoped to this workbook's worksheet, so a record id from another
    # workbook or tenant is simply not found.
    parent_worksheet = _get_worksheet(workbook, related_worksheet)
    parent = (
        db.query(Record)
        .filter(Record.id == related_record_id, Record.worksheet_id == parent_worksheet.id)
        .first()
    )
    if parent is None:
        raise _error(404, "NOT_FOUND", "Related record not found")

    rows = {worksheet_name: [IdentifiedRow(id=str(r.id), data=r.data) for r in records]}
    related_ids = {
        match["id"]
        for group in related_rows_for(related_worksheet, parent.data, config, rows)
        if group["entity"] == worksheet_name
        for match in group["records"]
    }
    return [r for r in records if str(r.id) in related_ids]


@router.get("/{workbook_id}/worksheets/{worksheet_name}/records", response_model=RecordPageOut)
def list_records(
    workbook_id: uuid.UUID,
    worksheet_name: str,
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    related_worksheet: str | None = Query(default=None),
    related_record_id: uuid.UUID | None = Query(default=None),
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

    if related_worksheet is not None or related_record_id is not None:
        records = _filter_related(db, workbook, config, worksheet_name, records, related_worksheet, related_record_id)

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
    all_records_by_entity: dict[str, list[IdentifiedRow]] = {
        e.worksheet: [
            IdentifiedRow(id=str(r.id), data=r.data)
            for r in db.query(Record)
            .join(Worksheet, Record.worksheet_id == Worksheet.id)
            .filter(Worksheet.workbook_id == workbook.id, Worksheet.name == e.worksheet)
            .all()
        ]
        for e in config.entities
    }

    related = related_rows_for(worksheet_name, record.data, config, all_records_by_entity)

    return {"id": str(record.id), "data": record.data, "related": related}
