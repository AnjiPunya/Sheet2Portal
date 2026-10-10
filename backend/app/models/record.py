import uuid

from sqlalchemy import JSON, ForeignKey, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Record(Base):
    """One parsed data row from a worksheet. Stores the full row (not just the
    preview sample) so KPI aggregation, search/filter and record detail views
    operate on actual uploaded data rather than a truncated preview.
    """

    __tablename__ = "records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    worksheet_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("worksheets.id"), nullable=False, index=True
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)

    worksheet: Mapped["Worksheet"] = relationship(back_populates="records")
