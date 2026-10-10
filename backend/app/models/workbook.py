import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class WorkbookStatus(str, enum.Enum):
    processing = "processing"
    ready = "ready"
    error = "error"


class Workbook(Base):
    __tablename__ = "workbooks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    stored_path: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[WorkbookStatus] = mapped_column(
        String, default=WorkbookStatus.processing, nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="workbooks")
    worksheets: Mapped[list["Worksheet"]] = relationship(
        back_populates="workbook", cascade="all, delete-orphan", order_by="Worksheet.sheet_index"
    )
