import uuid

from sqlalchemy import JSON, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Worksheet(Base):
    __tablename__ = "worksheets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workbook_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workbooks.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    sheet_index: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sample_rows: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    warning: Mapped[str | None] = mapped_column(String, nullable=True)

    workbook: Mapped["Workbook"] = relationship(back_populates="worksheets")
    columns: Mapped[list["Column"]] = relationship(
        back_populates="worksheet", cascade="all, delete-orphan", order_by="Column.position"
    )
    records: Mapped[list["Record"]] = relationship(
        back_populates="worksheet", cascade="all, delete-orphan", order_by="Record.row_index"
    )
