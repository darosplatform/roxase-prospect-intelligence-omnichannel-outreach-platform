"""Discovery Core API (C1: data contract only).

This router manages discovery jobs and their candidate sources. It performs NO
network fetch — candidate URLs are accepted, canonicalized and deduplicated. The
secure fetcher (SSRF/allowlist/timeouts) and the extractor are separate,
later chantiers. Nothing here writes into Lead/Score.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.crud_helpers import paginate
from app.api.deps import get_current_active_user, require_role
from app.db.session import get_db
from app.models.discovery import DiscoveryJob, DiscoverySource, RawDocument
from app.models.user import User
from app.schemas.discovery import (
    DiscoveryJobCreate,
    DiscoveryJobRead,
    DiscoveryJobUpdate,
    DiscoverySourceCreate,
    DiscoverySourceRead,
    ExtractionResultRead,
    RawDocumentCreate,
    RawDocumentRead,
)
from app.services import discovery as svc
from app.services import extraction as extraction_svc

router = APIRouter()


async def _get_job(db: AsyncSession, job_id: uuid.UUID, tenant_id: uuid.UUID) -> DiscoveryJob:
    job = await db.get(DiscoveryJob, job_id)
    if job is None or job.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Discovery job not found")
    return job


async def _get_source(
    db: AsyncSession, source_id: uuid.UUID, tenant_id: uuid.UUID
) -> DiscoverySource:
    source = await db.get(DiscoverySource, source_id)
    if source is None or source.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Discovery source not found")
    return source


@router.post("/discovery/jobs", response_model=DiscoveryJobRead, status_code=201)
async def create_discovery_job(
    payload: DiscoveryJobCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> DiscoveryJob:
    job = await svc.create_job(
        db,
        user.tenant_id,
        source_type=payload.source_type,
        target=payload.target,
        requested_by=payload.requested_by or user.id,
        options=payload.options,
    )
    await db.commit()
    await db.refresh(job)
    return job


@router.get("/discovery/jobs", response_model=list[DiscoveryJobRead])
async def list_discovery_jobs(
    skip: int = 0,
    limit: int = 50,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[DiscoveryJob]:
    stmt = select(DiscoveryJob).where(DiscoveryJob.tenant_id == user.tenant_id)
    if status:
        stmt = stmt.where(DiscoveryJob.status == status)
    stmt = stmt.order_by(DiscoveryJob.created_at.desc())
    stmt = paginate(stmt, skip, limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/discovery/jobs/{job_id}", response_model=DiscoveryJobRead)
async def get_discovery_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> DiscoveryJob:
    return await _get_job(db, job_id, user.tenant_id)


@router.patch("/discovery/jobs/{job_id}", response_model=DiscoveryJobRead)
async def transition_discovery_job(
    job_id: uuid.UUID,
    payload: DiscoveryJobUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> DiscoveryJob:
    job = await _get_job(db, job_id, user.tenant_id)
    if payload.status is not None:
        job = await svc.transition_job(db, job, payload.status)
    if payload.options is not None:
        job.options = payload.options
    await db.commit()
    await db.refresh(job)
    return job


@router.post(
    "/discovery/jobs/{job_id}/sources",
    response_model=list[DiscoverySourceRead],
    status_code=201,
)
async def add_discovery_sources(
    job_id: uuid.UUID,
    payload: list[DiscoverySourceCreate],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> list[DiscoverySource]:
    job = await _get_job(db, job_id, user.tenant_id)
    created = await svc.add_sources(
        db,
        job,
        [p.url for p in payload],
        source_name=payload[0].source_name if payload else None,
        discovered_via=payload[0].discovered_via if payload else None,
    )
    await db.commit()
    return created


@router.get(
    "/discovery/jobs/{job_id}/sources",
    response_model=list[DiscoverySourceRead],
)
async def list_discovery_sources(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[DiscoverySource]:
    job = await _get_job(db, job_id, user.tenant_id)
    return await svc.list_sources(db, user.tenant_id, job.id)


@router.get("/discovery/sources/{source_id}", response_model=DiscoverySourceRead)
async def get_discovery_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> DiscoverySource:
    return await _get_source(db, source_id, user.tenant_id)


@router.post("/discovery/sources/{source_id}/fetch", response_model=DiscoverySourceRead)
async def fetch_discovery_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> DiscoverySource:
    """Run the secure fetcher (C2) against this source's URL.

    Every candidate address is validated against SSRF safety rules before any
    byte is requested; on success a RawDocument is stored, on any safety or
    network failure the source is marked rejected/failed with the reason.
    No Evidence, Signal or Lead is created here.
    """
    source = await _get_source(db, source_id, user.tenant_id)
    source, _doc = await svc.fetch_source(db, user.tenant_id, source)
    return source


@router.post(
    "/discovery/sources/{source_id}/extract",
    response_model=ExtractionResultRead,
)
async def extract_discovery_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> ExtractionResultRead:
    """Run extraction (C3) against this source's most recent RawDocument.

    Produces/enriches a Company and any Contact candidates found on the
    page, plus one provenance-preserving Evidence record. Never creates a
    Signal or a Lead — that boundary belongs to C4/C5. 404s if no
    RawDocument has been captured for this source yet (run fetch first).
    """
    source = await _get_source(db, source_id, user.tenant_id)
    raw_document = await svc.get_latest_raw_document(db, user.tenant_id, source.id)
    if raw_document is None:
        raise HTTPException(
            status_code=409, detail="no RawDocument for this source yet; fetch it first"
        )
    outcome = await extraction_svc.ingest_raw_document(
        db, user.tenant_id, raw_document=raw_document, source=source
    )
    await db.commit()
    return ExtractionResultRead(
        company_id=outcome.company_id,
        contact_ids=outcome.contact_ids,
        evidence_id=outcome.evidence_id,
        page_type=outcome.page_type,
        skipped_reason=outcome.skipped_reason,
    )


@router.post("/discovery/raw", response_model=RawDocumentRead, status_code=201)
async def store_raw_document(
    payload: RawDocumentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> RawDocument:
    # Ownership guards: the source and job must both belong to this tenant,
    # and the source must belong to the given job.
    await _get_source(db, payload.source_id, user.tenant_id)
    job = await _get_job(db, payload.job_id, user.tenant_id)
    source = await db.get(DiscoverySource, payload.source_id)
    if source.job_id != job.id:
        raise HTTPException(status_code=409, detail="source does not belong to job")
    doc = await svc.store_raw_document(
        db,
        user.tenant_id,
        source_id=payload.source_id,
        job_id=payload.job_id,
        fetch_url=payload.fetch_url,
        content_type=payload.content_type,
        content_body=payload.content_body,
        http_status=payload.http_status,
    )
    await db.commit()
    return doc