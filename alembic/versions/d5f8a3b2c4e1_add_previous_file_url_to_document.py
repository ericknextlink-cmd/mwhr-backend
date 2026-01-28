"""Add previous_file_url to Document

Revision ID: d5f8a3b2c4e1
Revises: c4e8f2a1b3d0
Create Date: 2026-01-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5f8a3b2c4e1"
down_revision: Union[str, Sequence[str], None] = "c4e8f2a1b3d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document",
        sa.Column("previous_file_url", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document", "previous_file_url")
