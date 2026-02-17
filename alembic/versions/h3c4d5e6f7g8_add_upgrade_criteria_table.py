"""Add upgrade_criteria table

Revision ID: h3c4d5e6f7g8
Revises: g2b3c4d5e6f7
Create Date: 2026-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h3c4d5e6f7g8"
down_revision: Union[str, Sequence[str], None] = "g2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: table may already exist if created manually or from a previous run
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS upgrade_criteria (
            id SERIAL PRIMARY KEY,
            text VARCHAR NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS upgrade_criteria")
