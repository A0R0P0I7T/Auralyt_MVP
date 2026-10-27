"""Add prompt lifecycle_status and review_notes.

Revision ID: a8d2e4f617b9
Revises: f2a1b7c9d4e6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8d2e4f617b9"
down_revision: Union[str, Sequence[str], None] = "b5e3f2a1c9d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prompt_candidates", sa.Column("lifecycle_status", sa.String(length=32), nullable=False, server_default="approved"))
    op.add_column("prompt_candidates", sa.Column("review_notes", sa.Text(), nullable=True))
    op.create_index("ix_prompt_candidates_lifecycle_status", "prompt_candidates", ["lifecycle_status"])


def downgrade() -> None:
    op.drop_index("ix_prompt_candidates_lifecycle_status", table_name="prompt_candidates")
    op.drop_column("prompt_candidates", "review_notes")
    op.drop_column("prompt_candidates", "lifecycle_status")
