"""add_visibility_scans_and_results

Revision ID: e76192a54321
Revises: d45231558514
Create Date: 2026-10-11 20:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e76192a54321'
down_revision: Union[str, Sequence[str], None] = 'd45231558514'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add Engine 3 VisibilityScan and VisibilityResult tables."""
    op.create_table(
        'visibility_scans',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('brand_id', sa.String(length=36), nullable=False),
        sa.Column('profile_version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=False),
        sa.Column('model_name', sa.String(length=128), nullable=False),
        sa.Column('prompts_selected', sa.Integer(), nullable=False),
        sa.Column('prompts_completed', sa.Integer(), nullable=False),
        sa.Column('prompts_failed', sa.Integer(), nullable=False),
        sa.Column('visibility_score', sa.Float(), nullable=True),
        sa.Column('mention_rate', sa.Float(), nullable=True),
        sa.Column('recommendation_rate', sa.Float(), nullable=True),
        sa.Column('average_position', sa.Float(), nullable=True),
        sa.Column('total_tokens_used', sa.Integer(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('error_summary', sa.Text(), nullable=True),
        sa.Column('config_metadata', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_visibility_scans_brand_id'), 'visibility_scans', ['brand_id'], unique=False)
    op.create_index(op.f('ix_visibility_scans_status'), 'visibility_scans', ['status'], unique=False)
    op.create_index('ix_visibility_scans_brand_status', 'visibility_scans', ['brand_id', 'status'], unique=False)

    op.create_table(
        'visibility_results',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('scan_id', sa.String(length=36), nullable=False),
        sa.Column('brand_id', sa.String(length=36), nullable=False),
        sa.Column('prompt_id', sa.String(length=36), nullable=False),
        sa.Column('prompt_text', sa.Text(), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=False),
        sa.Column('model_name', sa.String(length=128), nullable=False),
        sa.Column('execution_status', sa.String(length=32), nullable=False),
        sa.Column('raw_response_text', sa.Text(), nullable=True),
        sa.Column('raw_response_metadata', sa.JSON(), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('error_details', sa.Text(), nullable=True),
        sa.Column('brand_mentioned', sa.Boolean(), nullable=False),
        sa.Column('mention_context', sa.Text(), nullable=True),
        sa.Column('recommendation_status', sa.String(length=32), nullable=False),
        sa.Column('competitor_mentions', sa.JSON(), nullable=False),
        sa.Column('comparative_position', sa.String(length=64), nullable=False),
        sa.Column('citations', sa.JSON(), nullable=False),
        sa.Column('sentiment_score', sa.Float(), nullable=True),
        sa.Column('visibility_rank', sa.Integer(), nullable=True),
        sa.Column('evaluation_reasoning', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['prompt_id'], ['prompt_candidates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scan_id'], ['visibility_scans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_visibility_results_brand_id'), 'visibility_results', ['brand_id'], unique=False)
    op.create_index(op.f('ix_visibility_results_scan_id'), 'visibility_results', ['scan_id'], unique=False)
    op.create_index(op.f('ix_visibility_results_prompt_id'), 'visibility_results', ['prompt_id'], unique=False)
    op.create_index(op.f('ix_visibility_results_brand_mentioned'), 'visibility_results', ['brand_mentioned'], unique=False)
    op.create_index(op.f('ix_visibility_results_recommendation_status'), 'visibility_results', ['recommendation_status'], unique=False)
    op.create_index('ix_visibility_results_brand_and_mention', 'visibility_results', ['brand_id', 'brand_mentioned'], unique=False)
    op.create_index('ix_visibility_results_scan_prompt', 'visibility_results', ['scan_id', 'prompt_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('visibility_results')
    op.drop_table('visibility_scans')
