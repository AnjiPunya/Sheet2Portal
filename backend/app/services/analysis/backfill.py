"""Self-heals workbooks whose worksheets have no persisted Record rows.

This covers workbooks uploaded before row-level persistence existed (the
`records` table was added after the initial upload/preview feature): their
Worksheet/Column rows and preview `sample_rows` are intact, but the full
row data was never written to `records`, so the portal-generation engine
(which only treats a sheet as usable once it has `rows`) silently produces
zero entities for a workbook that actually has perfectly good data.

Since the original uploaded file is always preserved on disk, the fix is to
re-parse it and backfill whatever's missing -- no data loss, no need to ask
the customer to re-upload.
"""

import uuid

from sqlalchemy.orm import Session

from app.models.record import Record
from app.models.workbook import Workbook
from app.services.parsing.service import extension_of, parse_workbook
from app.services.parsing.types import ParsingError
from app.services.storage.base import StorageBackend


def backfill_missing_records(db: Session, workbook: Workbook, storage: StorageBackend) -> bool:
    """Re-parse the original file and persist Records for any worksheet that
    has rows (row_count > 0) but no Record rows yet. Returns True if any
    worksheet was backfilled.
    """
    stale_worksheets = [
        ws
        for ws in workbook.worksheets
        if ws.row_count > 0 and db.query(Record).filter(Record.worksheet_id == ws.id).count() == 0
    ]
    if not stale_worksheets:
        return False

    ext = extension_of(workbook.original_filename)
    try:
        from app.core.config import settings

        result = parse_workbook(
            storage.path_for(workbook.stored_path), ext, settings.max_rows_per_sheet, settings.sample_row_count
        )
    except (ParsingError, OSError):
        # Original file is gone or no longer parseable -- can't self-heal;
        # the caller falls back to surfacing an explicit error instead.
        return False

    rows_by_sheet_name = {sheet.name: sheet.rows for sheet in result.sheets}
    backfilled = False
    for worksheet in stale_worksheets:
        rows = rows_by_sheet_name.get(worksheet.name)
        if not rows:
            continue
        db.bulk_insert_mappings(
            Record,
            [
                {"id": uuid.uuid4(), "worksheet_id": worksheet.id, "row_index": i, "data": row}
                for i, row in enumerate(rows)
            ],
        )
        backfilled = True

    if backfilled:
        db.commit()
    return backfilled
