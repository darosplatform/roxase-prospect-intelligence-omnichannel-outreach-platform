"""add outbox worker columns

Revision ID: a3f9c1e8d4b2
Revises: f861027429a7
Create Date: 2026-09-03 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = 'a3f9c1e8d4b2'
down_revision: Union[str, None] = 'f861027429a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('outreach_requests', sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('outreach_requests', sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('outreach_requests', sa.Column('attempt_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('outreach_requests', sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('outreach_requests', sa.Column('last_error', sa.Text(), nullable=True))
    op.add_column('outreach_requests', sa.Column('worker_id', sa.String(length=255), nullable=True))
    op.create_index(
        'ix_outreach_worker_claim',
        'outreach_requests',
        ['status', 'next_attempt_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_outreach_worker_claim', table_name='outreach_requests')
    op.drop_column('outreach_requests', 'worker_id')
    op.drop_column('outreach_requests', 'last_error')
    op.drop_column('outreach_requests', 'next_attempt_at')
    op.drop_column('outreach_requests', 'attempt_count')
    op.drop_column('outreach_requests', 'lease_until')
    op.drop_column('outreach_requests', 'claimed_at')