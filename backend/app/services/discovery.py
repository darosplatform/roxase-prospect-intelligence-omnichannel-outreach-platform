"""Discovery core orchestration (C1: data contract only).

Focused on lifecycle + provenance, with NO network fetch. Jobs and sources move
through validated state transitions; candidate URLs are canonicalized and
deduplicated; raw documents (captured later by the C2 fetcher) are stored with
their content hash for provability.

Single-writer discipline mirrors the outbox engine: transitions are scoped to the
current state so concurrent callers cannot double-advance a job/source.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.discovery_utils import content_hash, target_hash, url_hash
from app.core.metrics import metrics
from app.core.network_safety import SecureFetchError
from app.models.discovery import (
    DISCOVERY_JOB_STATUSES,
    DISCOVERY_SOURCE_STATUSES,
    DiscoveryJob,
    DiscoverySource,
    RawDocument,
)
from app.services.secure_fetcher import FetchResult, secure_fetch

VALID_JOB_TRANSITIONS = {
    "draft": ("queued", "cancelled"),
    "queued": ("running", "cancelled"),
    "running": ("fetched", "failed", "cancelled"),
    "fetched": ("extracted", "done", "failed", "cancelled"),
    "extracted": ("done", "failed", "cancelled"),
    "done": (),
    "failed": ("queued", "cancelled"),
    "cancelled": (),
}


def _check_job_transition(current: str, target: str) -> None:
    if current not in VALID_JOB_TRANSITIONS:
        raise HTTPException(status_code=409, detail=f"Invalid job status '{current}'")
    if target not in VALID_JOB_TRANSITIONS[current]:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition job '{current}' -> '{target}'",
        )


async def create_job(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    source_type: str,
    target: str,
    requested_by: uuid.UUID | None = None,
    options: dict | None = None,
    initial_status: str = "draft",
) -> DiscoveryJob:
    th = target_hash(target)
    existing = await db.execute(
        select(DiscoveryJob).where(
            DiscoveryJob.tenant_id == tenant_id,
            DiscoveryJob.target_hash == th,
        )
    )
    dup = existing.scalar_one_or_none()
    if dup is not None:
        return dup
    job = DiscoveryJob(
        tenant_id=tenant_id,
        source_type=source_type,
        target=target,
        target_hash=th,
        requested_by=requested_by,
        options=options,
        status=initial_status,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    return job


async def transition_job(
    db: AsyncSession,
    job: DiscoveryJob,
    new_status: str,
) -> DiscoveryJob:
    _check_job_transition(job.status, new_status)
    job.status = new_status
    if new_status in ("running",):
        job.started_at = None  # set by worker later
    elif new_status in ("done", "fetched", "extracted"):
        pass
    await db.flush()
    await db.refresh(job)
    return job


async def add_sources(
    db: AsyncSession,
    job: DiscoveryJob,
    urls: list[str],
    *,
    source_name: str | None = None,
    discovered_via: str | None = None,
    initial_status: str = "pending",
) -> list[DiscoverySource]:
    """Add candidate URLs to a job, canonicalizing + deduping per (tenant,url_hash)."""
    created: list[DiscoverySource] = []
    seen: set[str] = set()
    for raw in urls:
        uh = url_hash(raw)
        if uh in seen:
            continue
        seen.add(uh)
        existing = await db.execute(
            select(DiscoverySource.id).where(
                DiscoverySource.job_id == job.id,
                DiscoverySource.url_hash == uh,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue
        source = DiscoverySource(
            tenant_id=job.tenant_id,
            job_id=job.id,
            url=raw,
            url_hash=uh,
            source_name=source_name,
            discovered_via=discovered_via,
            status=initial_status,
        )
        db.add(source)
        created.append(source)
        await db.flush()
        await db.refresh(source)
    return created


async def list_sources(
    db: AsyncSession, tenant_id: uuid.UUID, job_id: uuid.UUID
) -> list[DiscoverySource]:
    result = await db.execute(
        select(DiscoverySource)
        .where(
            DiscoverySource.tenant_id == tenant_id,
            DiscoverySource.job_id == job_id,
        )
        .order_by(DiscoverySource.created_at.asc())
    )
    return list(result.scalars().all())


async def mark_source(
    db: AsyncSession,
    source: DiscoverySource,
    new_status: str,
    *,
    validation_status: str | None = None,
    rejection_reason: str | None = None,
) -> DiscoverySource:
    if new_status not in DISCOVERY_SOURCE_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown source status '{new_status}'")
    source.status = new_status
    if validation_status is not None:
        source.validation_status = validation_status
    if rejection_reason is not None:
        source.rejection_reason = rejection_reason
    await db.flush()
    await db.refresh(source)
    return source


async def store_raw_document(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    source_id: uuid.UUID,
    job_id: uuid.UUID,
    fetch_url: str,
    content_type: str | None,
    content_body: str | None,
    http_status: int | None = None,
) -> RawDocument:
    """Persist a raw document with a derived content hash; dedup per (tenant,hash)."""
    body = content_body or ""
    chash = content_hash(body)
    existing = await db.execute(
        select(RawDocument).where(
            RawDocument.tenant_id == tenant_id,
            RawDocument.content_hash == chash,
        )
    )
    dup = existing.scalar_one_or_none()
    if dup is not None:
        return dup
    doc = RawDocument(
        tenant_id=tenant_id,
        source_id=source_id,
        job_id=job_id,
        fetch_url=fetch_url,
        content_type=content_type,
        content_body=content_body,
        content_hash=chash,
        size_bytes=len(body.encode("utf-8")) if body else 0,
        http_status=http_status,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


async def fetch_source(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    source: DiscoverySource,
    *,
    fetcher=None,
) -> tuple[DiscoverySource, RawDocument | None]:
    """Run the secure fetcher (C2) against a source and persist the outcome.

    On success: stores a RawDocument with server-computed content_hash/size,
    marks the source "fetched" with its own copy of the fetch metadata.
    On any SecureFetchError (SSRF block, timeout, oversize, bad content-type,
    DNS failure, ...): marks the source "rejected" (blocked before any real
    exchange happened) or "failed" (the fetch was attempted and did not
    complete), records the reason, and creates NO RawDocument. Either way,
    this never creates Evidence, Signal, Lead or Score — that boundary is
    downstream of C2.
    """
    fetch_fn = fetcher or secure_fetch
    metrics.inc("discovery_fetch_total")
    try:
        result: FetchResult = await fetch_fn(source.url)
    except SecureFetchError as exc:
        if exc.code.startswith("blocked_") or exc.code in (
            "malformed_url",
            "blocked_scheme",
            "blocked_port",
            "blocked_content_type",
        ):
            metrics.inc("discovery_fetch_blocked_ssrf_total")
            new_status = "rejected"
        else:
            metrics.inc("discovery_fetch_failed_total")
            new_status = "failed"
        source = await mark_source(
            db,
            source,
            new_status,
            validation_status=exc.code,
            rejection_reason=exc.message,
        )
        await db.commit()
        return source, None

    decoded_body = result.body.decode("utf-8", errors="replace")
    doc = await store_raw_document(
        db,
        tenant_id,
        source_id=source.id,
        job_id=source.job_id,
        fetch_url=result.final_url,
        content_type=result.content_type,
        content_body=decoded_body,
        http_status=result.status_code,
    )
    source.status = "fetched"
    source.validation_status = "ok"
    source.http_status = result.status_code
    source.content_hash = doc.content_hash
    source.raw_size = len(result.body)
    source.fetched_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(source)
    await db.commit()
    metrics.inc("discovery_fetch_succeeded_total")
    metrics.inc("discovery_documents_total")
    metrics.set("discovery_fetch_latency_ms_last", int(result.elapsed_seconds * 1000))
    return source, doc


async def get_latest_raw_document(
    db: AsyncSession, tenant_id: uuid.UUID, source_id: uuid.UUID
) -> RawDocument | None:
    """Most recent RawDocument stored against this exact source_id.

    Note: `store_raw_document` dedups globally per (tenant, content_hash), so
    if this source's fetched content is byte-identical to a document already
    captured under a different source, that earlier document keeps its
    original source_id and nothing is returned here for THIS source — there
    is genuinely nothing new to extract for duplicate content.
    """
    result = await db.execute(
        select(RawDocument)
        .where(RawDocument.tenant_id == tenant_id, RawDocument.source_id == source_id)
        .order_by(RawDocument.fetched_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def list_job_statuses() -> list[str]:
    return list(DISCOVERY_JOB_STATUSES)