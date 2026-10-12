"""Separate provider grounding citations from response-text URLs.

Revision ID: a4c8e1f6b2d0
Revises: f2a1b7c9d4e6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4c8e1f6b2d0"
down_revision: Union[str, Sequence[str], None] = "f2a1b7c9d4e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("visibility_results", sa.Column("provider_citations", sa.JSON(), nullable=True))
    op.add_column("visibility_results", sa.Column("response_citations", sa.JSON(), nullable=True))
    op.execute("UPDATE visibility_results SET provider_citations = '[]' WHERE provider_citations IS NULL")
    op.execute("UPDATE visibility_results SET response_citations = '[]' WHERE response_citations IS NULL")


def downgrade() -> None:
    op.drop_column("visibility_results", "response_citations")
    op.drop_column("visibility_results", "provider_citations")
