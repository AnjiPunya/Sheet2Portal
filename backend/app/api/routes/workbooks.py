import io
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_tenant_id
from app.core.config import settings
from app.core.db import get_db
from app.models.column import Column
from app.models.record import Record
from app.models.workbook import Workbook, WorkbookStatus
from app.models.worksheet import Worksheet
from app.schemas.workbook import WorkbookOut
from app.services.parsing.service import extension_of, parse_workbook
from app.services.parsing.types import ParsingError
from app.services.storage.local import LocalStorageBackend

router = APIRouter(prefix="/api/workbooks", tags=["workbooks"])

storage = LocalStorageBackend(settings.upload_dir)


def _error(status_code: int, error_code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error_code": error_code, "message": message})


def _load_workbook(db: Session, workbook_id: uuid.UUID, tenant_id: uuid.UUID) -> Workbook:
    workbook = (
        db.query(Workbook)
        .options(selectinload(Workbook.worksheets).selectinload(Worksheet.columns))
        .filter(Workbook.id == workbook_id, Workbook.tenant_id == tenant_id)
        .first()
    )
    if workbook is None:
        raise _error(404, "NOT_FOUND", "Workbook not found")
    return workbook


@router.post("", response_model=WorkbookOut, status_code=201)
async def create_workbook(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
) -> Workbook:
    filename = file.filename or ""
    ext = extension_of(filename)
    if ext not in settings.allowed_extensions:
        raise _error(
            400,
            "UNSUPPORTED_FILE_TYPE",
            f"Unsupported file extension '{ext}'. Allowed: {', '.join(settings.allowed_extensions)}",
        )

    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise _error(
            413,
            "FILE_TOO_LARGE",
            f"File exceeds the {settings.max_upload_size_bytes // (1024 * 1024)}MB limit",
        )
    if len(content) == 0:
        raise _error(400, "EMPTY_WORKBOOK", "Uploaded file is empty")

    workbook_id = uuid.uuid4()
    stored_path = storage.save(str(tenant_id), str(workbook_id), filename, io.BytesIO(content))

    workbook = Workbook(
        id=workbook_id,
        tenant_id=tenant_id,
        original_filename=filename,
        stored_path=stored_path,
        status=WorkbookStatus.processing,
    )
    db.add(workbook)
    db.commit()

    try:
        result = parse_workbook(
            storage.path_for(stored_path), ext, settings.max_rows_per_sheet, settings.sample_row_count
        )
    except ParsingError as exc:
        workbook.status = WorkbookStatus.error
        workbook.error_code = exc.code
        workbook.error_message = str(exc)
        db.commit()
        return _load_workbook(db, workbook_id, tenant_id)

    for sheet in result.sheets:
        worksheet = Worksheet(
            workbook_id=workbook.id,
            name=sheet.name,
            sheet_index=sheet.sheet_index,
            row_count=sheet.row_count,
            sample_rows=sheet.sample_rows,
            warning=sheet.warning,
        )
        db.add(worksheet)
        db.flush()
        for col in sheet.columns:
            db.add(
                Column(
                    worksheet_id=worksheet.id,
                    name=col.name,
                    position=col.position,
                    inferred_type=col.inferred_type,
                    confidence=col.confidence,
                )
            )
        if sheet.rows:
            db.bulk_insert_mappings(
                Record,
                [
                    {"id": uuid.uuid4(), "worksheet_id": worksheet.id, "row_index": i, "data": row}
                    for i, row in enumerate(sheet.rows)
                ],
            )

    workbook.status = WorkbookStatus.ready
    db.commit()

    return _load_workbook(db, workbook_id, tenant_id)


@router.get("/{workbook_id}", response_model=WorkbookOut)
def get_workbook(
    workbook_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
) -> Workbook:
    return _load_workbook(db, workbook_id, tenant_id)
