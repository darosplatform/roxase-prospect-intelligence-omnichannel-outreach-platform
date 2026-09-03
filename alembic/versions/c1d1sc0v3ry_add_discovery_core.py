"""add discovery core (jobs, sources, raw documents)

Revision ID: c1d1sc0v3ry
Revises: a3f9c1e8d4b2
Create Date: 2026-09-03 17:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = 'c1d1sc0v3ry'
down_revision: Union[str, None] = 'a3f9c1e8d4b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # discovery_jobs
    op.create_table(
        'discovery_jobs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False),
        sa.Column('target', sa.Text(), nullable=False),
        sa.Column('target_hash', sa.String(length=128), nullable=False),
        sa.Column('requested_by', sa.Uuid(), nullable=True),
        sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('attempt_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id'], name='fk_discovery_requested_by', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_discovery_jobs_tenant_status', 'discovery_jobs', ['tenant_id', 'status'], unique=False)
    op.create_index('ix_discovery_jobs_tenant_created', 'discovery_jobs', ['tenant_id', 'created_at'], unique=False)
    op.create_index('uq_discovery_jobs_tenant_target', 'discovery_jobs', ['tenant_id', 'target_hash'], unique=True)

    # discovery_sources
    op.create_table(
        'discovery_sources',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('job_id', sa.Uuid(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('url_hash', sa.String(length=128), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('source_name', sa.String(length=255), nullable=True),
        sa.Column('discovered_via', sa.String(length=255), nullable=True),
        sa.Column('validation_status', sa.String(length=50), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('content_hash', sa.String(length=128), nullable=True),
        sa.Column('raw_size', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['discovery_jobs.id'], name='fk_source_job_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_discovery_sources_tenant_job', 'discovery_sources', ['tenant_id', 'job_id'], unique=False)
    op.create_index('uq_discovery_sources_job_hash', 'discovery_sources', ['job_id', 'url_hash'], unique=True)
    op.create_index('ix_discovery_sources_tenant_status', 'discovery_sources', ['tenant_id', 'status'], unique=False)

    # raw_documents
    op.create_table(
        'raw_documents',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('source_id', sa.Uuid(), nullable=False),
        sa.Column('job_id', sa.Uuid(), nullable=False),
        sa.Column('fetch_url', sa.Text(), nullable=False),
        sa.Column('content_type', sa.String(length=255), nullable=True),
        sa.Column('content_body', sa.Text(), nullable=True),
        sa.Column('content_hash', sa.String(length=128), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_id'], ['discovery_sources.id'], name='fk_raw_source_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['discovery_jobs.id'], name='fk_raw_job_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_raw_docs_tenant_source', 'raw_documents', ['tenant_id', 'source_id'], unique=False)
    op.create_index('uq_raw_docs_tenant_hash', 'raw_documents', ['tenant_id', 'content_hash'], unique=True)
    op.create_index('ix_raw_docs_tenant_fetched', 'raw_documents', ['tenant_id', 'fetched_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_raw_docs_tenant_fetched', table_name='raw_documents')
    op.drop_index('uq_raw_docs_tenant_hash', table_name='raw_documents')
    op.drop_index('ix_raw_docs_tenant_source', table_name='raw_documents')
    op.drop_table('raw_documents')

    op.drop_index('ix_discovery_sources_tenant_status', table_name='discovery_sources')
    op.drop_index('uq_discovery_sources_job_hash', table_name='discovery_sources')
    op.drop_index('ix_discovery_sources_tenant_job', table_name='discovery_sources')
    op.drop_table('discovery_sources')

    op.drop_index('uq_discovery_jobs_tenant_target', table_name='discovery_jobs')
    op.drop_index('ix_discovery_jobs_tenant_created', table_name='discovery_jobs')
    op.drop_index('ix_discovery_jobs_tenant_status', table_name='discovery_jobs')
    op.drop_table('discovery_jobs')