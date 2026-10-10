import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Column(Base):
    __tablename__ = "columns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    worksheet_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("worksheets.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    inferred_type: Mapped[str] = mapped_column(String, nullable=False, default="string")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    worksheet: Mapped["Worksheet"] = relationship(back_populates="columns")
