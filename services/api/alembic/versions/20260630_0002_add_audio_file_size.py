"""add audio file size

Revision ID: 20260630_0002
Revises: 20260630_0001
Create Date: 2026-06-30 17:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260630_0002"
down_revision: Union[str, None] = "20260630_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audio_files",
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.alter_column("audio_files", "file_size_bytes", server_default=None)


def downgrade() -> None:
    op.drop_column("audio_files", "file_size_bytes")
