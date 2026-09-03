"""Outreach control plane orchestration.

Separates decision from sending:

    Policy -> OutreachRequest(pending) -> approve -> queued
        -> dispatch (worker) -> provider.send -> sent / delivered / failed

A request denied by policy never reaches a provider. Dry-run simulates the
whole flow without contacting any external system. Every request is keyed by an
idempotency key so a replayed intention does not send twice.
"""

import hashlib
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.models.outreach_request import OutreachRequest
from app.models.policy_decision import PolicyDecision
from app.services import outbox
from app.services import policy as policy_mod


def make_idempotency_key(
    tenant_id: uuid.UUID,
    campaign_id: uuid.UUID | None,
    lead_id: uuid.UUID | None,
    contact_id: uuid.UUID | None,
    channel: str,
    template_id: uuid.UUID | None,
    logical_send_id: str,
) -> str:
    raw = {
        "tenant_id": str(tenant_id),
        "campaign_id": str(campaign_id),
        "lead_id": str(lead_id),
        "contact_id": str(contact_id),
        "channel": channel,
        "template_id": str(template_id),
        "logical_send_id": logical_send_id,
    }
    payload = "|".join(
        f"{k}={v}" for k, v in sorted(raw.items()) if v is not None and v != "None"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def persist_decision(db: AsyncSession, decision: policy_mod.Decision) -> PolicyDecision:
    actor_user_id = decision.meta.get("actor_user_id") if isinstance(decision.meta, dict) else None
    record = PolicyDecision(
        tenant_id=decision.tenant_id,
        lead_id=decision.lead_id,
        campaign_id=decision.campaign_id,
        contact_id=decision.contact_id,
        decision=decision.decision,
        policy_version=decision.policy_version,
        channel=decision.channel,
        score=decision.score,
        reasons=[
            {"code": r.code, "message": r.message, "severity": r.severity}
            for r in decision.reasons
        ],
        evidence_ids=[str(e) for e in decision.evidence_ids],
        created_by=actor_user_id,
    )
    db.add(record)
    await db.flush()
    return record


async def evaluate_and_persist(
    db: AsyncSession,
    *,
    lead,
    campaign,
    contact,
    channel: str,
    policy_input: policy_mod.PolicyInput,
    actor_user_id: uuid.UUID,
) -> tuple[policy_mod.Decision, PolicyDecision]:
    decision = policy_mod.evaluate(policy_input)
    decision.tenant_id = lead.tenant_id
    decision.lead_id = lead.id
    decision.campaign_id = campaign.id if campaign else None
    decision.contact_id = contact.id if contact else None
    decision.channel = channel
    decision.meta = {"actor_user_id": actor_user_id}

    record = await persist_decision(db, decision)
    await record_audit(
        db,
        tenant_id=lead.tenant_id,
        actor_user_id=actor_user_id,
        action="policy.evaluated",
        entity_type="policy_decision",
        entity_id=record.id,
        metadata={
            "decision": decision.decision,
            "policy_version": decision.policy_version,
            "score": decision.score,
            "evidence_ids": [str(e) for e in decision.evidence_ids],
            "campaign_id": str(decision.campaign_id),
            "channel": channel,
        },
    )
    return decision, record


async def find_by_idempotency(
    db: AsyncSession, tenant_id: uuid.UUID, key: str
) -> OutreachRequest | None:
    result = await db.execute(
        select(OutreachRequest).where(
            OutreachRequest.tenant_id == tenant_id,
            OutreachRequest.idempotency_key == key,
        )
    )
    return result.scalar_one_or_none()


async def dispatch_request(
    db: AsyncSession, req: OutreachRequest, dry_run: bool
) -> OutreachRequest:
    """Enqueue and execute an approved request via the outbox engine.

    This is a thin adapter over the outbox execution engine so the API route
    shares the SAME runtime authority as the background worker (`process_request`).
    There is no second, divergent dispatch path. `dry_run` is accepted for
    backwards compatibility but the global sticky `settings.dry_run` / kill
    switch remain authoritative inside the engine.
    """
    if req.status not in ("approved", "queued"):
        raise HTTPException(status_code=409, detail=f"Cannot dispatch status '{req.status}'")

    if req.status == "approved":
        req.status = "queued"
        await record_audit(
            db,
            tenant_id=req.tenant_id,
            actor_user_id=None,
            action="outreach.queued",
            entity_type="outreach_request",
            entity_id=req.id,
        )
        await db.flush()
        await db.commit()
        await db.refresh(req)

    claimed = await outbox.claim_requests(db, worker_id="api-sync", batch_size=1)
    target = next((r for r in claimed if r.id == req.id), None)
    if target is None:
        # Another authority already claimed/processed it; return the fresh state.
        await db.refresh(req)
        return req

    await outbox.process_request(db, target)
    await db.refresh(req)
    return req