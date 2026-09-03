"""Discovery core: jobs, sources and raw documents.

C1 scope: the DATA CONTRACT of the discovery pipeline. No network fetch happens
here — the secure fetcher/crawler is a later chantier. Jobs and sources carry
state, provenance and dedup metadata; raw documents store the fetched body
(captured by a future fetcher) alongside its content hash for provability.

The boundary is strict: discovery NEVER writes straight into Lead/Score. It only
produces raw data + provenance, which downstream stages turn into Evidence,
then Signals, then Leads.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DISCOVERY_JOB_STATUSES = (
    "draft",
    "queued",
    "running",
    "fetched",
    "extracted",
    "done",
    "failed",
    "cancelled",
)

DISCOVERY_SOURCE_STATUSES = (
    "pending",
    "eligible",
    "rejected",
    "fetched",
    "failed",
    "skipped",
)

SOURCE_TYPES = ("url", "sitemap", "rss", "api", "manual")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DiscoveryJob(Base):
    """A single discovery unit: a target (company/domain) and its candidate URLs."""

    __tablename__ = "discovery_jobs"
    __table_args__ = (
        Index("ix_discovery_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_discovery_jobs_tenant_created", "tenant_id", "created_at"),
        Index("uq_discovery_jobs_tenant_target", "tenant_id", "target_hash", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft", index=True
    )
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="url"
    )
    target: Mapped[str] = mapped_column(Text, nullable=False)
    target_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_discovery_requested_by"),
        nullable=True,
    )
    options: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Execution metadata (mirrors the outbox worker's durability fields).
    attempt_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class DiscoverySource(Base):
    """A candidate URL owned by a discovery job, with validation/fetch state."""

    __tablename__ = "discovery_sources"
    __table_args__ = (
        Index("ix_discovery_sources_tenant_job", "tenant_id", "job_id"),
        Index("uq_discovery_sources_job_hash", "job_id", "url_hash", unique=True),
        Index("ix_discovery_sources_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_jobs.id", ondelete="CASCADE", name="fk_source_job_id"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True
    )
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    discovered_via: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validation_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class RawDocument(Base):
    """The raw fetched body + provenance captured for a source (C2 will fill it)."""

    __tablename__ = "raw_documents"
    __table_args__ = (
        Index("ix_raw_docs_tenant_source", "tenant_id", "source_id"),
        Index("uq_raw_docs_tenant_hash", "tenant_id", "content_hash", unique=True),
        Index("ix_raw_docs_tenant_fetched", "tenant_id", "fetched_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_sources.id", ondelete="CASCADE", name="fk_raw_source_id"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_jobs.id", ondelete="CASCADE", name="fk_raw_job_id"),
        nullable=False,
        index=True,
    )
    fetch_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )