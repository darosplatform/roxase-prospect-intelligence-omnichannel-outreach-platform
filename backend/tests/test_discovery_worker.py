"""Discovery worker (C6) tests: claim, concurrency, lease recovery,
retry/backoff, dead-letter, success path, cancellation, idempotence.

Mirrors tests/test_outbox_worker.py's structure and coverage exactly, since
discovery_worker.py deliberately reuses the same claim/lease/retry model.
The worker engine is exercised directly against the test DB via `db_session`,
with the network layer (secure_fetch) faked so the C2/C3/C4 chain runs for
real but with zero real sockets.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.discovery_utils import target_hash, url_hash
from app.core.metrics import metrics
from app.models.discovery import DiscoveryJob, DiscoverySource, RawDocument
from app.models.evidence import Evidence
from app.models.signal import Signal
from app.models.tenant import Tenant
from app.services import discovery as discovery_svc
from app.services import discovery_worker as worker
from app.services.secure_fetcher import FetchResult, SecureFetchError

HTML_PAGE = """
<html><head><title>Acme raises Series A</title>
<meta property="og:site_name" content="Acme Robotics" /></head>
<body><p>Acme raised a $10M Series A round. Contact
<a href="mailto:jane@acme.com">jane@acme.com</a></p></body></html>
"""

# Deliberately no autouse metrics.reset() fixture here: Metrics.reset() wipes
# the ENTIRE process-wide registry, including the module-level counters/
# gauges other test files (e.g. test_observability.py) depend on being
# present regardless of test run order. Every metrics assertion below uses
# ">= 1" against monotonically-increasing counters, so no baseline reset is
# needed.


async def _seed_tenant(session, slug: str, name: str) -> Tenant:
    tenant = Tenant(slug=slug, name=name)
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return tenant


async def _seed_job(
    session, tenant_id: uuid.UUID, target: str, *, status: str = "queued", attempt: int = 0
) -> DiscoveryJob:
    job = DiscoveryJob(
        tenant_id=tenant_id,
        status=status,
        source_type="url",
        target=target,
        target_hash=target_hash(target),
        attempt_count=attempt,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def _seed_source(session, job: DiscoveryJob, url: str, *, status: str = "pending"):
    source = DiscoverySource(
        tenant_id=job.tenant_id, job_id=job.id, url=url, url_hash=url_hash(url), status=status
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


def _fake_fetch_ok(body: bytes = HTML_PAGE.encode()):
    async def _fetch(url, **_kwargs):
        return FetchResult(
            final_url=url,
            status_code=200,
            content_type="text/html",
            body=body,
            resolved_ip="93.184.216.34",
            redirect_chain=[],
            elapsed_seconds=0.01,
        )

    return _fetch


async def _job_status(session, job_id) -> str:
    row = await session.get(DiscoveryJob, job_id)
    return row.status


# --------------------------------------------------------------------------- #
# A. unique claim under two workers
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_claim_unique_two_workers_one_job(db_session):
    tenant = await _seed_tenant(db_session, "dw-uniq", "DW Unique")
    job = await _seed_job(db_session, tenant.id, "https://acme.com")

    claimed_a = await worker.claim_jobs(db_session, worker_id="worker-a", batch_size=10)
    claimed_b = await worker.claim_jobs(db_session, worker_id="worker-b", batch_size=10)

    assert len(claimed_a) == 1
    assert claimed_a[0].id == job.id
    assert claimed_a[0].worker_id == "worker-a"
    assert claimed_b == []
    assert (await _job_status(db_session, job.id)) == "running"


# --------------------------------------------------------------------------- #
# B. lease recovery after crash
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_lease_recovery_after_crash(db_session, monkeypatch):
    tenant = await _seed_tenant(db_session, "dw-lease", "DW Lease")
    job = await _seed_job(db_session, tenant.id, "https://acme.com")
    monkeypatch.setattr(settings, "worker_lease_seconds", 1)
    monkeypatch.setattr(discovery_svc, "secure_fetch", _fake_fetch_ok())

    claimed_a = await worker.claim_jobs(db_session, worker_id="worker-a", batch_size=10)
    assert len(claimed_a) == 1

    # Worker A "crashes": never processes. Expire its lease in DB.
    job.lease_until = datetime.now(UTC) - timedelta(seconds=5)
    await db_session.commit()

    processed = await worker.run_once(db_session, worker_id="worker-b", batch_size=10)
    assert processed == 1
    assert (await _job_status(db_session, job.id)) == "done"
    assert metrics.count(worker.RECOVERED) >= 1


# --------------------------------------------------------------------------- #
# C. success path: fetch -> extract -> detect-signal -> done
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_success_path_creates_full_chain(db_session, monkeypatch):
    tenant = await _seed_tenant(db_session, "dw-ok", "DW Success")
    job = await _seed_job(db_session, tenant.id, "https://acme.com")
    await _seed_source(db_session, job, "https://acme.com/news/series-a")
    monkeypatch.setattr(discovery_svc, "secure_fetch", _fake_fetch_ok())

    processed = await worker.run_once(db_session, worker_id="worker-a", batch_size=10)
    assert processed == 1
    assert (await _job_status(db_session, job.id)) == "done"

    docs = (
        await db_session.execute(
            select(RawDocument).where(RawDocument.tenant_id == tenant.id)
        )
    ).scalars().all()
    assert len(docs) == 1

    evs = (
        await db_session.execute(select(Evidence).where(Evidence.tenant_id == tenant.id))
    ).scalars().all()
    assert len(evs) == 1

    sigs = (
        await db_session.execute(select(Signal).where(Signal.tenant_id == tenant.id))
    ).scalars().all()
    assert len(sigs) == 1
    assert sigs[0].signal_type == "funding"
    assert sigs[0].evidence_id == evs[0].id


@pytest.mark.asyncio
async def test_success_path_multiple_sources_all_processed(db_session, monkeypatch):
    tenant = await _seed_tenant(db_session, "dw-multi", "DW Multi")
    job = await _seed_job(db_session, tenant.id, "https://acme.com")
    await _seed_source(db_session, job, "https://acme.com/news/a")
    await _seed_source(db_session, job, "https://acme.com/news/b")
    monkeypatch.setattr(discovery_svc, "secure_fetch", _fake_fetch_ok())

    await worker.run_once(db_session, worker_id="worker-a", batch_size=10)

    sources = (
        await db_session.execute(
            select(DiscoverySource).where(DiscoverySource.job_id == job.id)
        )
    ).scalars().all()
    assert all(s.status == "fetched" for s in sources)


@pytest.mark.asyncio
async def test_ssrf_blocked_source_does_not_fail_the_job(db_session, monkeypatch):
    """One source being SSRF-blocked is a valid per-source outcome, not a
    worker fault: the job still completes, other sources still process."""
    tenant = await _seed_tenant(db_session, "dw-ssrf", "DW SSRF")
    job = await _seed_job(db_session, tenant.id, "https://acme.com")
    await _seed_source(db_session, job, "https://acme.com/blocked")
    await _seed_source(db_session, job, "https://acme.com/ok")

    calls = {"n": 0}

    async def flaky_fetch(url, **_kwargs):
        calls["n"] += 1
        if "blocked" in url:
            raise SecureFetchError("blocked_private", "blocked for the test")
        return FetchResult(
            final_url=url,
            status_code=200,
            content_type="text/html",
            body=HTML_PAGE.encode(),
            resolved_ip="93.184.216.34",
            redirect_chain=[],
            elapsed_seconds=0.01,
        )

    monkeypatch.setattr(discovery_svc, "secure_fetch", flaky_fetch)

    processed = await worker.run_once(db_session, worker_id="worker-a", batch_size=10)
    assert processed == 1
    assert (await _job_status(db_session, job.id)) == "done"

    sources = (
        await db_session.execute(
            select(DiscoverySource).where(DiscoverySource.job_id == job.id)
        )
    ).scalars().all()
    statuses = {s.status for s in sources}
    assert statuses == {"rejected", "fetched"}


# --------------------------------------------------------------------------- #
# D. retry + exponential backoff with ceiling, then dead-letter
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_retry_backoff_and_dead_letter_on_worker_fault(db_session, monkeypatch):
    tenant = await _seed_tenant(db_session, "dw-retry", "DW Retry")
    job = await _seed_job(db_session, tenant.id, "https://acme.com")
    await _seed_source(db_session, job, "https://acme.com/x")
    monkeypatch.setattr(settings, "worker_base_backoff", 2.0)
    monkeypatch.setattr(settings, "worker_max_backoff", 7.0)
    monkeypatch.setattr(settings, "worker_max_attempts", 2)

    async def boom(url, **_kwargs):
        raise RuntimeError("simulated worker fault")

    monkeypatch.setattr(discovery_svc, "secure_fetch", boom)

    claimed = await worker.claim_jobs(db_session, worker_id="worker-a", batch_size=10)
    status = await worker.process_job(db_session, claimed[0])
    assert status == "queued"
    assert (await _job_status(db_session, job.id)) == "queued"
    assert claimed[0].attempt_count == 1

    job.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    claimed = await worker.claim_jobs(db_session, worker_id="worker-a", batch_size=10)
    status = await worker.process_job(db_session, claimed[0])
    assert status == "failed"
    assert (await _job_status(db_session, job.id)) == "failed"
    assert metrics.count(worker.FAILED) >= 1
    assert metrics.count(worker.RETRIED) >= 1


# --------------------------------------------------------------------------- #
# E. cancellation / idempotence: terminal jobs are never reclaimed
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_cancelled_job_never_claimed(db_session):
    tenant = await _seed_tenant(db_session, "dw-cancel", "DW Cancel")
    await _seed_job(db_session, tenant.id, "https://acme.com", status="cancelled")
    claimed = await worker.claim_jobs(db_session, worker_id="worker-a", batch_size=10)
    assert claimed == []


@pytest.mark.asyncio
async def test_done_job_never_reclaimed(db_session):
    tenant = await _seed_tenant(db_session, "dw-done", "DW Done")
    await _seed_job(db_session, tenant.id, "https://acme.com", status="done")
    claimed = await worker.claim_jobs(db_session, worker_id="worker-a", batch_size=10)
    assert claimed == []


@pytest.mark.asyncio
async def test_concurrency_n_workers_n_jobs_no_double_processing(db_session, monkeypatch):
    tenant = await _seed_tenant(db_session, "dw-conc", "DW Concurrency")
    jobs = []
    for i in range(4):
        j = await _seed_job(db_session, tenant.id, f"https://acme{i}.com")
        await _seed_source(db_session, j, f"https://acme{i}.com/news/x")
        jobs.append(j)
    monkeypatch.setattr(discovery_svc, "secure_fetch", _fake_fetch_ok())

    processed_a = await worker.run_once(db_session, worker_id="worker-a", batch_size=2)
    processed_b = await worker.run_once(db_session, worker_id="worker-b", batch_size=2)

    assert processed_a + processed_b == 4
    rows = (
        await db_session.execute(select(DiscoveryJob).where(DiscoveryJob.tenant_id == tenant.id))
    ).scalars().all()
    assert all(r.status == "done" for r in rows)
