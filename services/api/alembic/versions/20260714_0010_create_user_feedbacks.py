"""create user feedbacks

Revision ID: 20260714_0010
Revises: 20260702_0009
Create Date: 2026-07-14 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260714_0010"
down_revision: str | None = "20260702_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_feedbacks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("feedback_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("contact", sa.String(length=255), nullable=True),
        sa.Column("image_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_feedbacks_feedback_type"), "user_feedbacks", ["feedback_type"], unique=False)
    op.create_index(op.f("ix_user_feedbacks_status"), "user_feedbacks", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_feedbacks_status"), table_name="user_feedbacks")
    op.drop_index(op.f("ix_user_feedbacks_feedback_type"), table_name="user_feedbacks")
    op.drop_table("user_feedbacks")
