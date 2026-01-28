"""Add tutorials_completed to User

Revision ID: c4e8f2a1b3d0
Revises: bb41ba8cdbbf
Create Date: 2026-01-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4e8f2a1b3d0"
down_revision: Union[str, Sequence[str], None] = "bb41ba8cdbbf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("tutorials_completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("user", "tutorials_completed")
