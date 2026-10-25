"""Pin profile snapshots and add auditable fact lifecycle metadata.

Revision ID: f2a1b7c9d4e6
Revises: e76192a54321
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a1b7c9d4e6"
down_revision: Union[str, Sequence[str], None] = "e76192a54321"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("profile_runs", sa.Column("profile_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("profile_runs", sa.Column("crawl_summary", sa.JSON(), nullable=True))
    op.create_index("ix_profile_runs_profile_version", "profile_runs", ["profile_version"])
    op.execute("UPDATE profile_runs SET crawl_summary = '{}' WHERE crawl_summary IS NULL")

    op.add_column("brand_facts", sa.Column("fact_key", sa.String(length=512), nullable=True))
    op.add_column("brand_facts", sa.Column("supporting_evidence", sa.JSON(), nullable=True))
    op.add_column("brand_facts", sa.Column("is_rejected", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("brand_facts", sa.Column("is_superseded", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("brand_facts", sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("brand_facts", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("brand_facts", sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_brand_facts_fact_key", "brand_facts", ["fact_key"])
    op.create_index("ix_brand_facts_is_rejected", "brand_facts", ["is_rejected"])
    op.execute("UPDATE brand_facts SET supporting_evidence = '[]' WHERE supporting_evidence IS NULL")


def downgrade() -> None:
    op.drop_index("ix_brand_facts_is_rejected", table_name="brand_facts")
    op.drop_index("ix_brand_facts_fact_key", table_name="brand_facts")
    op.drop_column("brand_facts", "superseded_at")
    op.drop_column("brand_facts", "last_seen_at")
    op.drop_column("brand_facts", "is_stale")
    op.drop_column("brand_facts", "is_superseded")
    op.drop_column("brand_facts", "is_rejected")
    op.drop_column("brand_facts", "supporting_evidence")
    op.drop_column("brand_facts", "fact_key")
    op.drop_index("ix_profile_runs_profile_version", table_name="profile_runs")
    op.drop_column("profile_runs", "crawl_summary")
    op.drop_column("profile_runs", "profile_version")
