"""add action_drafts for assistant draft -> confirm -> execute

Additive only: one new table.

Revision ID: c5f3e4a6b7d8
Revises: b4e2d3f5a6c7
Create Date: 2026-10-11 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5f3e4a6b7d8"
down_revision: Union[str, None] = "b4e2d3f5a6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "action_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workbook_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("worksheet", sa.String(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("preview", sa.JSON(), nullable=False),
        sa.Column("record_hash", sa.String(), nullable=True),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["workbook_id"], ["workbooks.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_action_drafts_conversation", "action_drafts", ["user_id", "workbook_id", "conversation_id", "status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_action_drafts_conversation", table_name="action_drafts")
    op.drop_table("action_drafts")
