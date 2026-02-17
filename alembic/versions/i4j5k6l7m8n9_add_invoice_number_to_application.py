"""Add invoice_number to application

Revision ID: i4j5k6l7m8n9
Revises: h3c4d5e6f7g8
Create Date: 2026-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i4j5k6l7m8n9"
down_revision: Union[str, Sequence[str], None] = "h3c4d5e6f7g8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("application", sa.Column("invoice_number", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("application", "invoice_number")
