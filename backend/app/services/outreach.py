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
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.config import settings
from app.models.contact import Contact
from app.models.outreach_request import OutreachRequest
from app.models.policy_decision import PolicyDecision
from app.services import policy as policy_mod
from app.services.providers import Message, registry


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
    """Execute an approved request through the outbox -> provider flow."""
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

    # Kill switch: block real sends, still allow dry-run simulation.
    if dry_run or not settings.outreach_enabled:
        req.status = "sent"
        req.sent_at = datetime.now(UTC)
        req.provider_message_id = f"dry_run:{req.id}"
        await record_audit(
            db,
            tenant_id=req.tenant_id,
            action="outreach.simulated",
            entity_type="outreach_request",
            entity_id=req.id,
            metadata={"dry_run": True},
        )
        await db.flush()
        return req

    req.status = "dispatching"
    await db.flush()

    provider = registry.provider_for(req.channel)
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
        req.sent_at = datetime.now(UTC)
        req.provider_message_id = result.provider_message_id
        await record_audit(
            db,
            tenant_id=req.tenant_id,
            action="outreach.sent",
            entity_type="outreach_request",
            entity_id=req.id,
            metadata={"provider_message_id": result.provider_message_id},
        )
    else:
        req.status = "failed"
        await record_audit(
            db,
            tenant_id=req.tenant_id,
            action="outreach.failed",
            entity_type="outreach_request",
            entity_id=req.id,
            metadata={"error": result.error},
        )
    await db.flush()
    return req


async def _recipient(db: AsyncSession, req: OutreachRequest) -> str:
    if req.contact_id:
        contact = await db.get(Contact, req.contact_id)
        if contact is not None and contact.email:
            return contact.email
    return req.idempotency_key or str(req.id)