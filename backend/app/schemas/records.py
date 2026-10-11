from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RecordWriteIn(BaseModel):
    data: dict = Field(default_factory=dict)


class DecisionIn(BaseModel):
    action: Literal["approve", "reject", "resubmit"]
    comment: str | None = Field(default=None, max_length=1000)


class RecordActionsOut(BaseModel):
    edit: bool
    delete: bool
    approve: bool
    reject: bool
    resubmit: bool


class RecordWriteOut(BaseModel):
    id: str
    data: dict
    actions: RecordActionsOut


class RecordEventOut(BaseModel):
    id: str
    action: str
    user_name: str
    from_status: str | None
    to_status: str | None
    comment: str | None
    changes: dict
    created_at: datetime


class RecordActivityOut(BaseModel):
    actions: RecordActionsOut
    history: list[RecordEventOut]
