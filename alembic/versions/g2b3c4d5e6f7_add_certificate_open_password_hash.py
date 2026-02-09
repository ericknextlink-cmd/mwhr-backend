"""Add certificate_open_password_hash to Application

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "application",
        sa.Column("certificate_open_password_hash", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("application", "certificate_open_password_hash")
