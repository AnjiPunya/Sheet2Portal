import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ActionDraft(Base):
    """A change the assistant (chat or voice) has prepared but not made.

    Created by the planner from the model's ``propose_action`` tool call;
    executed only after the user confirms *this exact draft* with its
    one-time token (stored hashed). Scoped to one user, workbook and
    conversation. A correction creates a new draft and supersedes the old
    one, so a confirmation always refers to the content the user last saw.

    status: pending -> executing -> completed | failed
            pending -> cancelled | superseded | expired
    """

    __tablename__ = "action_drafts"
    __table_args__ = (Index("ix_action_drafts_conversation", "user_id", "workbook_id", "conversation_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    workbook_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("workbooks.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)  # create|update|delete|approve|reject|resubmit
    worksheet: Mapped[str] = mapped_column(String, nullable=False)
    record_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)  # what the record service receives
    preview: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)  # what the user was shown
    record_hash: Mapped[str | None] = mapped_column(String, nullable=True)  # target record's data when drafted
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
