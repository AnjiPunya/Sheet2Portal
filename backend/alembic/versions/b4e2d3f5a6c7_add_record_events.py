"""add record_events audit trail

Additive only: one new table.

Revision ID: b4e2d3f5a6c7
Revises: a3f1c2d4e5b6
Create Date: 2026-10-11 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4e2d3f5a6c7"
down_revision: Union[str, None] = "a3f1c2d4e5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "record_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workbook_id", sa.Uuid(), nullable=False),
        sa.Column("worksheet", sa.String(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("user_name", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("from_status", sa.String(), nullable=True),
        sa.Column("to_status", sa.String(), nullable=True),
        sa.Column("comment", sa.String(), nullable=True),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["workbook_id"], ["workbooks.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_record_events_tenant_id"), "record_events", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_record_events_workbook_id"), "record_events", ["workbook_id"], unique=False)
    op.create_index(op.f("ix_record_events_record_id"), "record_events", ["record_id"], unique=False)
    op.create_index(op.f("ix_record_events_created_at"), "record_events", ["created_at"], unique=False)


def downgrade() -> None:
    for index in ("created_at", "record_id", "workbook_id", "tenant_id"):
        op.drop_index(op.f(f"ix_record_events_{index}"), table_name="record_events")
    op.drop_table("record_events")
