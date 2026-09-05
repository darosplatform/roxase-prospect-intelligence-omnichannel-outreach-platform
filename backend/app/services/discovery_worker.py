"""Discovery outbox engine (C6): the durable, asynchronous execution path for
queued DiscoveryJobs. Reuses the exact same claim/lease/retry/backoff model
as the outreach outbox (`app/services/outbox.py`) — same atomic
UPDATE...RETURNING single-winner claim, same expired-lease crash recovery,
same exponential backoff with a terminal `failed` state. No new
infrastructure (no Celery/Kafka/queue broker): same Postgres, same asyncio
loop shape, a second lightweight polling process.

For each claimed job, every "pending"/"eligible" source is walked through
the full C2->C3->C4 chain (fetch -> extract -> detect-signal) one at a time.
A single source's SSRF block, fetch failure, or unsupported content type is
an expected, terminal, PER-SOURCE outcome — not a worker error — so it never
triggers job-level retry/backoff; the job simply moves on to the next
source. Job-level retry/backoff is reserved for genuine worker faults
(a DB error, an unexpected exception) that leave a source's true outcome
undetermined. Never creates a Lead or touches scoring — C4's own boundary
(Evidence -> Signal only) is untouched here.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import metrics
from app.models.discovery import DiscoveryJob, DiscoverySource
from app.models.evidence import Evidence
from app.services import discovery as discovery_svc
from app.services import extraction as extraction_svc
from app.services import signal_detection

logger = logging.getLogger("roxase.discovery_worker")

CLAIMED = "discovery_worker_claimed_total"
RECOVERED = "discovery_worker_recovered_total"
COMPLETED = "discovery_jobs_total"
FAILED = "discovery_jobs_failed_total"
RETRIED = "discovery_worker_retried_total"

# Source statuses that still need work; anything else (fetched/rejected/
# failed/skipped) is already terminal for this source and is left alone.
_PENDING_SOURCE_STATUSES = ("pending", "eligible")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _backoff_delay(attempt: int) -> float:
    delay = settings.worker_base_backoff * (2 ** max(0, attempt - 1))
    return min(delay, settings.worker_max_backoff)


async def claim_jobs(
    db: AsyncSession, worker_id: str, batch_size: int | None = None
) -> list[DiscoveryJob]:
    """Atomically claim up to `batch_size` due DiscoveryJobs.

    Due candidates are `queued` rows whose `next_attempt_at` is NULL or due,
    plus `running` rows whose lease has expired (recovery of a crashed
    peer). Each candidate is flipped `-> running` in an atomic UPDATE
    re-scoped to its current status, so a row contended between two workers
    is claimed by exactly one — identical single-winner guarantee to the
    outreach outbox.
    """
    batch_size = batch_size or settings.worker_batch_size
    now = _utcnow()
    lease_until = now + timedelta(seconds=settings.worker_lease_seconds)

    cand = await db.execute(
        select(DiscoveryJob.id, DiscoveryJob.status)
        .where(
            DiscoveryJob.status.in_(("queued", "running")),
            or_(
                and_(
                    DiscoveryJob.status == "queued",
                    or_(
                        DiscoveryJob.next_attempt_at.is_(None),
                        DiscoveryJob.next_attempt_at <= now,
                    ),
                ),
                and_(
                    DiscoveryJob.status == "running",
                    DiscoveryJob.lease_until.is_not(None),
                    DiscoveryJob.lease_until < now,
                ),
            ),
        )
        .order_by(DiscoveryJob.updated_at.asc())
        .limit(batch_size)
    )
    candidates = list(cand.all())

    claimed_ids: list[uuid.UUID] = []
    for job_id, status in candidates:
        was_recovered = status == "running"
        result = await db.execute(
            update(DiscoveryJob)
            .where(DiscoveryJob.id == job_id, DiscoveryJob.status == status)
            .values(
                status="running",
                claimed_at=now,
                lease_until=lease_until,
                worker_id=worker_id,
                started_at=DiscoveryJob.started_at if was_recovered else now,
            )
            .returning(DiscoveryJob.id)
        )
        if result.fetchall():
            claimed_ids.append(job_id)
            metrics.inc(CLAIMED)
            if was_recovered:
                metrics.inc(RECOVERED)

    await db.commit()
    if not claimed_ids:
        return []
    rows = await db.execute(select(DiscoveryJob).where(DiscoveryJob.id.in_(claimed_ids)))
    return list(rows.scalars())


async def _process_source(
    db: AsyncSession, tenant_id: uuid.UUID, source: DiscoverySource
) -> None:
    source, raw_document = await discovery_svc.fetch_source(db, tenant_id, source)
    if source.status != "fetched" or raw_document is None:
        return  # a rejected/failed fetch is a valid, terminal per-source outcome

    outcome = await extraction_svc.ingest_raw_document(
        db, tenant_id, raw_document=raw_document, source=source
    )
    await db.commit()
    if outcome.evidence_id is None:
        return  # unsupported content type: nothing further to detect on

    evidence = await db.get(Evidence, outcome.evidence_id)
    if evidence is not None:
        await signal_detection.ingest_evidence(db, tenant_id, evidence)
        await db.commit()


async def process_job(db: AsyncSession, job: DiscoveryJob) -> str:
    """Execute one claimed job: walk every pending source through
    fetch -> extract -> detect-signal, then transition the job to a
    terminal state. Assumes `job` was already atomically claimed
    (`status == "running"`).
    """
    result = await db.execute(
        select(DiscoverySource).where(
            DiscoverySource.job_id == job.id,
            DiscoverySource.status.in_(_PENDING_SOURCE_STATUSES),
        )
    )
    sources = list(result.scalars().all())

    try:
        for source in sources:
            await _process_source(db, job.tenant_id, source)
    except Exception as exc:  # worker fault, not a per-source outcome
        return await _mark_retry(db, job, str(exc))

    # Walk the job's own declared state machine in full (running -> fetched
    # -> extracted -> done) via the same transition_job used everywhere
    # else, rather than jumping straight to a terminal status.
    job.lease_until = None
    job.claimed_at = None
    await discovery_svc.transition_job(db, job, "fetched")
    await discovery_svc.transition_job(db, job, "extracted")
    await discovery_svc.transition_job(db, job, "done")
    job.finished_at = _utcnow()
    await db.commit()
    metrics.inc(COMPLETED)
    return "done"


async def _mark_retry(db: AsyncSession, job: DiscoveryJob, error: str) -> str:
    job.attempt_count += 1
    if job.attempt_count >= settings.worker_max_attempts:
        job.status = "failed"
        job.last_error = error
        job.lease_until = None
        job.claimed_at = None
        job.finished_at = _utcnow()
        await db.commit()
        metrics.inc(FAILED)
        return "failed"

    delay = _backoff_delay(job.attempt_count)
    job.status = "queued"
    job.next_attempt_at = _utcnow() + timedelta(seconds=delay)
    job.last_error = error
    job.lease_until = None
    job.claimed_at = None
    job.worker_id = None
    await db.commit()
    metrics.inc(RETRIED)
    return "queued"


async def run_once(db: AsyncSession, worker_id: str, batch_size: int | None = None) -> int:
    """Claim then process a batch of DiscoveryJobs; return how many were
    handled. Each claimed job commits its own progress so a crash mid-batch
    never loses an unrelated job's state."""
    claimed = await claim_jobs(db, worker_id, batch_size)
    for job in claimed:
        await process_job(db, job)
    return len(claimed)
