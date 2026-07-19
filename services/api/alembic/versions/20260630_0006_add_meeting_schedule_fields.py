"""add meeting schedule fields

Revision ID: 20260630_0006
Revises: 20260630_0005
Create Date: 2026-06-30 23:40:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260630_0006"
down_revision: Union[str, None] = "20260630_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("meetings", sa.Column("start_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("meetings", sa.Column("end_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("meetings", sa.Column("location", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("meetings", "location")
    op.drop_column("meetings", "end_at")
    op.drop_column("meetings", "start_at")
