"""add discovery worker columns (lease/claim, mirrors the outbox worker)

Revision ID: 9f2b7c4a1d6e
Revises: c1d1sc0v3ry
Create Date: 2026-09-05 09:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = '9f2b7c4a1d6e'
down_revision: Union[str, None] = 'c1d1sc0v3ry'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # attempt_count/next_attempt_at/last_error already exist on discovery_jobs
    # (C1). Only the claim/lease columns are new, added purely additively so
    # discovery_worker.py can claim jobs with the exact same atomic
    # UPDATE...RETURNING pattern the outreach outbox worker already uses.
    op.add_column('discovery_jobs', sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('discovery_jobs', sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('discovery_jobs', sa.Column('worker_id', sa.String(length=255), nullable=True))
    op.create_index(
        'ix_discovery_worker_claim',
        'discovery_jobs',
        ['status', 'next_attempt_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_discovery_worker_claim', table_name='discovery_jobs')
    op.drop_column('discovery_jobs', 'worker_id')
    op.drop_column('discovery_jobs', 'lease_until')
    op.drop_column('discovery_jobs', 'claimed_at')
