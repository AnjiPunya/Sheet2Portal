import uuid

from pydantic import BaseModel, ConfigDict


class ColumnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    position: int
    inferred_type: str
    confidence: float


class WorksheetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    sheet_index: int
    row_count: int
    warning: str | None
    columns: list[ColumnOut]
    sample_rows: list[dict]


class WorkbookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    status: str
    error_code: str | None
    error_message: str | None
    worksheets: list[WorksheetOut]


class ErrorResponse(BaseModel):
    error_code: str
    message: str
