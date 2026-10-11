import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    display_title: str | None
    status: str
    error_code: str | None
    error_message: str | None
    worksheets: list[WorksheetOut]


class WorkbookSummaryOut(BaseModel):
    """One row in the signed-in user's list of portals."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    display_title: str | None
    status: str
    created_at: datetime


class WorkbookTitleUpdate(BaseModel):
    """PATCH body for customizing a portal's title. An empty/whitespace-only
    title resets to the generated default rather than storing a blank name."""

    title: str | None = Field(default=None, max_length=200)


class ErrorResponse(BaseModel):
    error_code: str
    message: str
