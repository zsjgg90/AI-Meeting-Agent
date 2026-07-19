"""create speaker mappings

Revision ID: 20260630_0005
Revises: 20260630_0004
Create Date: 2026-06-30 19:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260630_0005"
down_revision: Union[str, None] = "20260630_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "speaker_mappings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("speaker_label", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "speaker_label", name="uq_speaker_mappings_meeting_label"),
    )
    op.create_index(op.f("ix_speaker_mappings_meeting_id"), "speaker_mappings", ["meeting_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_speaker_mappings_meeting_id"), table_name="speaker_mappings")
    op.drop_table("speaker_mappings")
