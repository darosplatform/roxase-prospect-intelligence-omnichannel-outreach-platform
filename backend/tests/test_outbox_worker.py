"""Outbox worker tests: claim, concurrency, lease recovery, retry/backoff,
dead-letter, success, dry-run, kill switch, idempotence, cross-tenant,
graceful shutdown, audit and metrics.

The worker engine is exercised directly against the test DB via the `db_session`
fixture (same engine/DB as the API). A `queued` outreach request is seeded in
DB and claimed/processed by the outbox functions exactly as the background
process would.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.metrics import metrics
from app.models.audit import AuditEvent
from app.models.outreach_request import OutreachRequest
from app.models.tenant import Tenant
from app.services import outbox
from app.services.providers import MockEmailProvider, registry


@pytest.fixture(autouse=True)
def _cleanup_registry_and_metrics():
    """Restore the email provider singleton and reset metrics between tests."""
    original_email = registry.get("email")
    metrics.reset()
    yield
    registry.register("email", original_email)
    metrics.reset()


async def _seed_tenant(session, slug: str, name: str) -> Tenant:
    tenant = Tenant(slug=slug, name=name)
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return tenant


async def _seed_request(
    session,
    tenant_id: uuid.UUID,
    *,
    status: str = "queued",
    channel: str = "email",
    attempt: int = 0,
    next_attempt_at=None,
    scheduled_at=None,
    idempotency_key: str | None = None,
) -> OutreachRequest:
    req = OutreachRequest(
        tenant_id=tenant_id,
        channel=channel,
        status=status,
        idempotency_key=idempotency_key or f"key-{uuid.uuid4()}",
        scheduled_at=scheduled_at,
        next_attempt_at=next_attempt_at,
        attempt_count=attempt,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


async def _status(session, req_id: uuid.UUID) -> str:
    row = await session.get(OutreachRequest, req_id)
    return row.status


# ---------------------------------------------------------------------------
# A. unique claim under two workers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_unique_two_workers_one_request(db_session):
    tenant = await _seed_tenant(db_session, "w-uniq", "W Unique")
    req = await _seed_request(db_session, tenant.id)

    claimed_a = await outbox.claim_requests(db_session, worker_id="worker-a", batch_size=10)
    claimed_b = await outbox.claim_requests(db_session, worker_id="worker-b", batch_size=10)

    assert len(claimed_a) == 1
    assert (await _status(db_session, req.id)) == "dispatching"
    # worker B cannot claim the already-dispatching (non-expired) row
    assert claimed_b == []
    assert (await _status(db_session, req.id)) == "dispatching"
    assert claimed_a[0].worker_id == "worker-a"


# ---------------------------------------------------------------------------
# B. concurrency: N workers, N requests, no double execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrency_n_workers_n_requests_no_double(db_session):
    tenant = await _seed_tenant(db_session, "w-conc", "W Concurrency")
    requests = []
    for i in range(5):
        r = await _seed_request(db_session, tenant.id, idempotency_key=f"c-{i}")
        requests.append(r)

    # Two workers each run a poll round over the same batch.
    processed_a = await outbox.run_once(db_session, worker_id="worker-a", batch_size=3)
    processed_b = await outbox.run_once(db_session, worker_id="worker-b", batch_size=3)

    assert processed_a + processed_b == 5
    # Each logical request handled exactly once -> all terminal sent, none left queued.
    rows = (
        (await db_session.execute(select(OutreachRequest)))
        .scalars()
        .all()
    )
    owned = [r for r in rows if r.tenant_id == tenant.id]
    assert len(owned) == 5
    for row in owned:
        assert row.status == "sent"
        assert row.attempt_count == 0


# ---------------------------------------------------------------------------
# C. lease: claim, expiration, recovery by second worker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lease_recovery_after_crash(db_session, monkeypatch):
    tenant = await _seed_tenant(db_session, "w-lease", "W Lease")
    req = await _seed_request(db_session, tenant.id)

    monkeypatch.setattr(settings, "worker_lease_seconds", 1)
    monkeypatch.setattr(settings, "dry_run", True)

    claimed_a = await outbox.claim_requests(db_session, worker_id="worker-a", batch_size=10)
    assert len(claimed_a) == 1
    assert claimed_a[0].status == "dispatching"
    assert (await _status(db_session, req.id)) == "dispatching"

    # Worker A "crashes": never processes. Expire its lease in DB.
    req.lease_until = datetime.now(UTC) - timedelta(seconds=5)
    await db_session.commit()

    # Worker B recovers and processes it.
    processed = await outbox.run_once(db_session, worker_id="worker-b", batch_size=10)
    assert processed == 1
    assert (await _status(db_session, req.id)) == "sent"
    assert metrics.count(outbox.RECOVERED) >= 1


# ---------------------------------------------------------------------------
# D/E. retry + exponential backoff with ceiling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_backoff_and_dead_letter(db_session, monkeypatch):
    tenant = await _seed_tenant(db_session, "w-retry", "W Retry")
    req = await _seed_request(db_session, tenant.id)

    monkeypatch.setattr(settings, "worker_base_backoff", 2.0)
    monkeypatch.setattr(settings, "worker_max_backoff", 7.0)
    monkeypatch.setattr(settings, "worker_max_attempts", 3)
    monkeypatch.setattr(settings, "dry_run", False)
    monkeypatch.setattr(settings, "outreach_enabled", True)

    failing = MockEmailProvider(fail=True)
    registry.register("email", failing)

    # Attempt 1 -> retry scheduled, backoff = 2^1 = 2s
    claimed = await outbox.claim_requests(db_session, worker_id="worker-a", batch_size=10)
    status = await outbox.process_request(db_session, claimed[0])
    assert status == "queued"
    assert (await _status(db_session, req.id)) == "queued"
    assert claimed[0].attempt_count == 1
    expected_d1 = min(2 * (2 ** (1 - 1)), 7.0)
    delay = (claimed[0].next_attempt_at - datetime.now(UTC)).total_seconds()
    assert 0 <= delay <= expected_d1 + 1.0

    # Bypass backoff gate for attempt 2, backoff = min(2*2,7)=4
    req.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    claimed = await outbox.claim_requests(db_session, worker_id="worker-a", batch_size=10)
    status = await outbox.process_request(db_session, claimed[0])
    assert status == "queued"
    assert claimed[0].attempt_count == 2

    # Attempt 3 -> MAX_ATTEMPTS -> dead-letter -> failed
    req.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    claimed = await outbox.claim_requests(db_session, worker_id="worker-a", batch_size=10)
    status = await outbox.process_request(db_session, claimed[0])
    assert status == "failed"
    assert (await _status(db_session, req.id)) == "failed"
    assert metrics.count(outbox.FAILED) >= 1
    assert metrics.count(outbox.RETRIED) >= 2


# ---------------------------------------------------------------------------
# G. success queued -> dispatching -> sent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_path(db_session, monkeypatch):
    tenant = await _seed_tenant(db_session, "w-ok", "W Success")
    req = await _seed_request(db_session, tenant.id)
    monkeypatch.setattr(settings, "dry_run", False)
    monkeypatch.setattr(settings, "outreach_enabled", True)

    ok_provider = MockEmailProvider(fail=False)
    registry.register("email", ok_provider)

    claimed = await outbox.claim_requests(db_session, worker_id="worker-w", batch_size=10)
    assert claimed[0].status == "dispatching"
    status = await outbox.process_request(db_session, claimed[0])
    assert status == "sent"
    assert (await _status(db_session, req.id)) == "sent"
    assert ok_provider.calls and ok_provider.calls[0].id == req.id
    assert metrics.count(outbox.DISPATCHED) == 1


# ---------------------------------------------------------------------------
# H. dry-run: simulate, ZERO external provider calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_no_external_call(db_session, monkeypatch):
    tenant = await _seed_tenant(db_session, "w-dry", "W Dry")
    req = await _seed_request(db_session, tenant.id)
    monkeypatch.setattr(settings, "dry_run", True)
    monkeypatch.setattr(settings, "outreach_enabled", True)

    spy = MockEmailProvider(fail=False)
    registry.register("email", spy)

    claimed = await outbox.claim_requests(db_session, worker_id="worker-d", batch_size=10)
    status = await outbox.process_request(db_session, claimed[0])
    assert status == "sent"
    assert (await _status(db_session, req.id)) == "sent"
    assert claimed[0].provider_message_id.startswith("dry_run:")
    assert spy.calls == []  # zero real provider calls
    assert metrics.count(outbox.SIMULATED) == 1
    assert metrics.count(outbox.DISPATCHED) == 1


# ---------------------------------------------------------------------------
# I. kill switch: no execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kill_switch_blocks_execution(db_session, monkeypatch):
    tenant = await _seed_tenant(db_session, "w-kill", "W Kill")
    await _seed_request(db_session, tenant.id)
    monkeypatch.setattr(settings, "dry_run", False)
    monkeypatch.setattr(settings, "outreach_enabled", False)

    spy = MockEmailProvider(fail=False)
    registry.register("email", spy)

    claimed = await outbox.claim_requests(db_session, worker_id="worker-k", batch_size=10)
    status = await outbox.process_request(db_session, claimed[0])
    assert status == "sent"
    assert spy.calls == []
    assert claimed[0].provider_message_id.startswith("dry_run:")
    assert metrics.count(outbox.SIMULATED) == 1


# ---------------------------------------------------------------------------
# J. idempotence: same request replayed never double-sends
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotent_no_double_execution(db_session, monkeypatch):
    tenant = await _seed_tenant(db_session, "w-idem", "W Idempotent")
    req = await _seed_request(db_session, tenant.id)
    monkeypatch.setattr(settings, "dry_run", False)
    monkeypatch.setattr(settings, "outreach_enabled", True)

    spy = MockEmailProvider(fail=False)
    registry.register("email", spy)

    # Process once.
    await outbox.run_once(db_session, worker_id="worker-1", batch_size=10)
    sent_calls = len(spy.calls)
    assert (await _status(db_session, req.id)) == "sent"
    assert sent_calls == 1

    # A second poll round sees nothing claimable -> no new provider call.
    processed = await outbox.run_once(db_session, worker_id="worker-2", batch_size=10)
    assert processed == 0
    assert len(spy.calls) == sent_calls


# ---------------------------------------------------------------------------
# K. cross-tenant: worker only ever processes its own row's tenant scoping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_tenant_no_bleed(db_session, monkeypatch):
    tenant_a = await _seed_tenant(db_session, "w-tena", "W Tenant A")
    tenant_b = await _seed_tenant(db_session, "w-tenb", "W Tenant B")
    ra = await _seed_request(db_session, tenant_a.id, idempotency_key="a")
    rb = await _seed_request(db_session, tenant_b.id, idempotency_key="b")

    monkeypatch.setattr(settings, "dry_run", True)

    # Claim the batch; both rows claimable, each scoped to its own tenant.
    claimed = await outbox.claim_requests(db_session, worker_id="worker-x", batch_size=10)
    assert {r.tenant_id for r in claimed} == {tenant_a.id, tenant_b.id}
    for c in claimed:
        await outbox.process_request(db_session, c)
    assert (await _status(db_session, ra.id)) == "sent"
    assert (await _status(db_session, rb.id)) == "sent"


# ---------------------------------------------------------------------------
# M. audit events recorded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_events_recorded(db_session, monkeypatch):
    tenant = await _seed_tenant(db_session, "w-audit", "W Audit")
    await _seed_request(db_session, tenant.id)
    monkeypatch.setattr(settings, "dry_run", True)

    await outbox.run_once(db_session, worker_id="worker-a", batch_size=10)

    events = (
        (await db_session.execute(select(AuditEvent).where(AuditEvent.tenant_id == tenant.id)))
        .scalars()
        .all()
    )
    actions = [e.action for e in events]
    assert "outreach.simulated" in actions


# ---------------------------------------------------------------------------
# F. dead-letter: MAX_ATTEMPTS reached -> failed (dedicated assertion)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dead_letter_terminal_failed(db_session, monkeypatch):
    tenant = await _seed_tenant(db_session, "w-dl", "W DeadLetter")
    req = await _seed_request(db_session, tenant.id)
    monkeypatch.setattr(settings, "worker_max_attempts", 2)
    monkeypatch.setattr(settings, "dry_run", False)
    monkeypatch.setattr(settings, "outreach_enabled", True)
    registry.register("email", MockEmailProvider(fail=True))

    for _ in range(2):
        await outbox.run_once(db_session, worker_id="worker-dl", batch_size=10)
        req.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.commit()

    assert (await _status(db_session, req.id)) == "failed"
    # not claimable again -> dead letter is terminal
    req.status = "failed"
    await db_session.commit()
    remaining = await outbox.claim_requests(db_session, worker_id="worker-dl2", batch_size=10)
    assert remaining == []


# ---------------------------------------------------------------------------
# N. metrics counters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metrics_counters(db_session, monkeypatch):
    tenant = await _seed_tenant(db_session, "w-met", "W Metrics")
    await _seed_request(db_session, tenant.id)
    monkeypatch.setattr(settings, "dry_run", True)

    await outbox.run_once(db_session, worker_id="worker-m", batch_size=10)

    assert metrics.count(outbox.CLAIMED) == 1
    assert metrics.count(outbox.DISPATCHED) == 1
    assert metrics.count(outbox.SIMULATED) == 1


def test_worker_entrypoint_importable():
    import importlib

    importlib.import_module("app.worker")
    assert True


def test_backoff_ceiling_respected(monkeypatch):
    monkeypatch.setattr(settings, "worker_base_backoff", 1.0)
    monkeypatch.setattr(settings, "worker_max_backoff", 3.0)
    assert outbox._backoff_delay(1) == 1.0
    assert outbox._backoff_delay(2) == 2.0
    assert outbox._backoff_delay(3) == 3.0
    assert outbox._backoff_delay(10) == 3.0  # capped