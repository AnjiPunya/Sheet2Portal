"""Loads a workbook's persisted worksheets/columns/records out of the DB and
into the plain dataclasses the analysis engine operates on, keeping the
engine itself free of any ORM dependency (and therefore easy to unit test).
"""

from sqlalchemy.orm import Session

from app.models.record import Record
from app.models.workbook import Workbook
from app.services.analysis.types import SheetData


def load_sheet_data(db: Session, workbook: Workbook) -> list[SheetData]:
    sheets: list[SheetData] = []
    for worksheet in workbook.worksheets:
        if not worksheet.columns:
            continue
        records = (
            db.query(Record)
            .filter(Record.worksheet_id == worksheet.id)
            .order_by(Record.row_index)
            .all()
        )
        sheets.append(
            SheetData(
                name=worksheet.name,
                columns=[(c.name, c.inferred_type, c.confidence) for c in worksheet.columns],
                rows=[r.data for r in records],
            )
        )
    return sheets
