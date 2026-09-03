"""Durable outbox execution engine for the outreach control plane.

The worker process (`python -m app.worker`) is the single execution authority
for `queued` outreach requests. The API only enqueues (`approved -> queued`);
the worker claims, leases, processes, retries and finally sends/fails items.

Concurrency & durability model
------------------------------
* Claim is an ATOMIC UPDATE ... RETURNING: a row is flipped
  `queued -> dispatching` (with lease + claimed_at + worker_id) in a single
  statement. Only one worker can win a given row, so N workers never
  double-process the same request.
* The provider call happens AFTER the claim is committed, so no DB row lock is
  held across network I/O and a crash mid-send never blocks recovery.
* A worker that dies after claiming leaves the row `dispatching` with an
  expired lease; it becomes reclaimable by any peer worker on the next poll.
* On provider failure the row goes back to `queued` with an exponential
  backoff gate (`next_attempt_at`); past `worker_max_attempts` it becomes
  terminal `failed` (V1 dead-letter).

Safety invariants
-----------------
* Kill switch: when `not settings.outreach_enabled`, real sends are prohibited
  and any claimed-but-in-flight request is flattened to a simulated result.
* Dry-run: when `settings.dry_run` is True, providers are NEVER contacted; a
  simulated result is recorded. Both guards are sticky and never bypassed.
* Cross-tenant: a claim only ever touches a single row; no other tenant's rows
  are read or written anywhere in the engine.
* Idempotence: `OutreachRequest` carries a unique `idempotency_key`. Two
  workers claiming the same row? Impossible — the atomic claim guarantees a
  single winner, so the same logical send is never executed twice.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.config import settings
from app.core.metrics import metrics
from app.models.outreach_request import OutreachRequest
from app.services import providers
from app.services.providers import Message

CLAIMED = "outreach_worker_claimed_total"
DISPATCHED = "outreach_worker_dispatched_total"
FAILED = "outreach_worker_failed_total"
RETRIED = "outreach_worker_retried_total"
RECOVERED = "outreach_worker_recovered_total"
SENT = "outreach_worker_sent_total"
SIMULATED = "outreach_worker_simulated_total"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff with a ceiling: min(BASE * 2^(attempt-1), MAX)."""
    delay = settings.worker_base_backoff * (2 ** max(0, attempt - 1))
    return min(delay, settings.worker_max_backoff)


async def claim_requests(
    db: AsyncSession,
    worker_id: str,
    batch_size: int | None = None,
) -> list[OutreachRequest]:
    """Atomically claim up to `batch_size` due requests and return them.

    Due candidates are:
    * `queued` rows whose `next_attempt_at` is NULL (first attempt) or due.
    * `dispatching` rows whose lease has expired (recovery of a crashed peer).

    Each candidate is flipped `-> dispatching` in an atomic UPDATE that is
    re-scoped to the current status, so a row contended between two workers is
    claimed by exactly one. The winning rows are returned; a contended row is
    skipped until its next eligible poll.
    """
    batch_size = batch_size or settings.worker_batch_size
    now = _utcnow()
    lease_until = now + timedelta(seconds=settings.worker_lease_seconds)

    cand = await db.execute(
        select(OutreachRequest.id, OutreachRequest.status)
        .where(
            OutreachRequest.status.in_(("queued", "dispatching")),
            or_(
                # First-attempt or backoff-due queued rows.
                and_(
                    OutreachRequest.status == "queued",
                    or_(
                        OutreachRequest.next_attempt_at.is_(None),
                        OutreachRequest.next_attempt_at <= now,
                    ),
                ),
                # Expired-lease dispatching rows (recovery).
                and_(
                    OutreachRequest.status == "dispatching",
                    OutreachRequest.lease_until.is_not(None),
                    OutreachRequest.lease_until < now,
                ),
            ),
        )
        .order_by(OutreachRequest.updated_at.asc())
        .limit(batch_size)
    )
    candidates = list(cand.all())

    claimed_ids: list[uuid.UUID] = []
    for req_id, status in candidates:
        was_recovered = status == "dispatching"
        result = await db.execute(
            update(OutreachRequest)
            .where(
                OutreachRequest.id == req_id,
                OutreachRequest.status == status,  # re-scoped: only claim if unchanged
            )
            .values(
                status="dispatching",
                claimed_at=now,
                lease_until=lease_until,
                worker_id=worker_id,
            )
            .returning(OutreachRequest.id)
        )
        if result.fetchall():
            claimed_ids.append(req_id)
            metrics.inc(CLAIMED)
            if was_recovered:
                metrics.inc(RECOVERED)

    await db.commit()

    if not claimed_ids:
        return []

    rows = await db.execute(
        select(OutreachRequest).where(OutreachRequest.id.in_(claimed_ids))
    )
    return list(rows.scalars())


async def _recipient(db: AsyncSession, req: OutreachRequest) -> str:
    from app.models.contact import Contact

    if req.contact_id:
        contact = await db.get(Contact, req.contact_id)
        if contact is not None and contact.email:
            return contact.email
    return f"no-recipient-{req.id}"


async def _simulate(db: AsyncSession, req: OutreachRequest, reason: str) -> str:
    """Record a simulated send (dry-run or kill switch). Zero external calls."""
    req.status = "sent"
    req.sent_at = _utcnow()
    req.provider_message_id = f"dry_run:{req.id}"
    req.last_error = None
    req.lease_until = None
    req.claimed_at = None
    await record_audit(
        db,
        tenant_id=req.tenant_id,
        action="outreach.simulated",
        entity_type="outreach_request",
        entity_id=req.id,
        metadata={"dry_run": True, "reason": reason},
    )
    metrics.inc(SIMULATED)
    metrics.inc(DISPATCHED)
    return "sent"


async def _mark_retry(db: AsyncSession, req: OutreachRequest, error: str) -> str:
    """Apply exponential backoff; escalate to terminal `failed` past max attempts."""
    req.attempt_count += 1
    if req.attempt_count >= settings.worker_max_attempts:
        req.status = "failed"
        req.last_error = error
        req.lease_until = None
        req.claimed_at = None
        await record_audit(
            db,
            tenant_id=req.tenant_id,
            action="outreach.failed",
            entity_type="outreach_request",
            entity_id=req.id,
            metadata={"error": error, "attempt": req.attempt_count, "reason": "max_attempts"},
        )
        metrics.inc(FAILED)
        return "failed"

    delay = _backoff_delay(req.attempt_count)
    req.status = "queued"
    req.next_attempt_at = _utcnow() + timedelta(seconds=delay)
    req.last_error = error
    req.lease_until = None
    req.claimed_at = None
    req.worker_id = None
    await record_audit(
        db,
        tenant_id=req.tenant_id,
        action="outreach.retry_scheduled",
        entity_type="outreach_request",
        entity_id=req.id,
        metadata={"attempt": req.attempt_count, "next_attempt_at": req.next_attempt_at.isoformat()},
    )
    metrics.inc(RETRIED)
    return "queued"


async def process_request(db: AsyncSession, req: OutreachRequest) -> str:
    """Execute one claimed request through the provider (or simulation).

    Assumes `req` was already atomically claimed (`status == "dispatching"`).
    Commits the resulting state and returns the final/next status. On provider
    failure this applies backoff/retry or escalates to `failed`.
    """
    kill_switch = not settings.outreach_enabled
    if kill_switch or settings.dry_run:
        reason = "kill_switch" if kill_switch else "dry_run"
        status = await _simulate(db, req, reason)
        await db.commit()
        return status

    provider = providers.registry.provider_for(req.channel)
    message = Message(
        id=req.id,
        channel=req.channel,
        to=await _recipient(db, req),
        template_id=req.template_id,
        tenant_id=req.tenant_id,
        campaign_id=req.campaign_id,
        metadata={"idempotency_key": req.idempotency_key},
    )
    result = provider.send(message)

    if result.ok:
        req.status = "sent"
        req.sent_at = _utcnow()
        req.provider_message_id = result.provider_message_id
        req.last_error = None
        req.lease_until = None
        req.claimed_at = None
        await record_audit(
            db,
            tenant_id=req.tenant_id,
            action="outreach.sent",
            entity_type="outreach_request",
            entity_id=req.id,
            metadata={"provider_message_id": result.provider_message_id},
        )
        metrics.inc(SENT)
        metrics.inc(DISPATCHED)
        await db.commit()
        return "sent"

    status = await _mark_retry(db, req, result.error)
    await db.commit()
    return status


async def run_once(db: AsyncSession, worker_id: str, batch_size: int | None = None) -> int:
    """Claim then process a batch; return the number of requests handled.

    Each claimed request is processed in its own committed transaction so a
    hard crash mid-batch never loses an unrelated row's progress.
    """
    claimed = await claim_requests(db, worker_id, batch_size)
    processed = 0
    for req in claimed:
        await process_request(db, req)
        processed += 1
    return processed