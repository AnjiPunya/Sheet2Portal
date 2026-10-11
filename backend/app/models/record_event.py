import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RecordEvent(Base):
    """Audit trail: one row per create/update/delete and per workflow
    decision (approve/reject/resubmit). Append-only. `record_id` is not a
    foreign key so a deleted record's history survives."""

    __tablename__ = "record_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False, index=True)
    workbook_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("workbooks.id"), nullable=False, index=True)
    worksheet: Mapped[str] = mapped_column(String, nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    user_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    action: Mapped[str] = mapped_column(String, nullable=False)  # created|updated|deleted|approved|rejected|resubmitted
    from_status: Mapped[str | None] = mapped_column(String, nullable=True)
    to_status: Mapped[str | None] = mapped_column(String, nullable=True)
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    changes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)  # field -> [old, new]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
