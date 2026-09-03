import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.crud_helpers import apply_sort, paginate
from app.api.deps import get_current_active_user
from app.api.validators import (
    assert_campaign_in_tenant,
    assert_contact_in_tenant,
    assert_lead_in_tenant,
)
from app.core.config import settings
from app.db.session import get_db
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.do_not_contact import DoNotContact
from app.models.lead import Lead
from app.models.policy_decision import PolicyDecision
from app.models.signal import Signal
from app.models.user import User
from app.schemas.policy import (
    PolicyDecisionRead,
    PolicyEvaluateRequest,
    PolicyEvaluateResponse,
)
from app.services import policy as policy_mod
from app.services.outreach import evaluate_and_persist

router = APIRouter()

SORT_FIELDS = {"created_at": PolicyDecision.created_at, "decision": PolicyDecision.decision}


async def _get_owned_lead(db: AsyncSession, lead_id: uuid.UUID, tenant_id) -> Lead:
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


async def _get_entity(db, model, entity_id: uuid.UUID):
    result = await db.execute(select(model).where(model.id == entity_id))
    return result.scalar_one_or_none()


def _days_old(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    return (datetime.now(UTC) - dt).total_seconds() / 86400.0


async def _gather_context(
    db: AsyncSession, lead: Lead, tenant_id: uuid.UUID
) -> tuple[list[Signal], float | None, dict]:
    """Collect tenant-scoped signals + evidence freshness for the lead's company."""
    signals_result = await db.execute(
        select(Signal).where(
            Signal.tenant_id == tenant_id,
            Signal.deleted_at.is_(None),
            Signal.status != "dismissed",
        )
    )
    signals = [
        s for s in signals_result.scalars().all()
        if lead.company_id is not None and s.company_id == lead.company_id
    ]
    if not signals:
        return [], None, {}

    relevant_evidence: dict = {}
    newest = max(signals, key=lambda s: s.detected_at or datetime.min)
    for signal in signals:
        if signal.evidence_id:
            relevant_evidence[str(signal.evidence_id)] = {"signal_type": signal.signal_type}
    freshness_days = _days_old(newest.detected_at)
    return signals, freshness_days, relevant_evidence


async def _frequency_exceeded(
    db, tenant_id, campaign, contact, lead, channel, max_per_day: int | None
) -> list[str]:
    if max_per_day is None:
        return []
    from datetime import timedelta

    from app.models.outreach_request import OutreachRequest

    since = datetime.now(UTC) - timedelta(days=1)
    stmt = select(OutreachRequest).where(
        OutreachRequest.tenant_id == tenant_id,
        OutreachRequest.channel == channel,
        OutreachRequest.created_at >= since,
        OutreachRequest.status.in_(["sent", "queued", "dispatching"]),
    )
    if contact is not None:
        stmt = stmt.where(OutreachRequest.contact_id == contact.id)
    elif campaign is not None:
        stmt = stmt.where(OutreachRequest.campaign_id == campaign.id)
    count = len(list((await db.execute(stmt)).scalars().all()))
    if count >= max_per_day:
        return ["FREQUENCY_LIMIT"]
    return []


async def _build_policy_input(
    db, lead, campaign, contact, channel, tenant_id
) -> tuple[policy_mod.PolicyInput, dict]:
    signals, freshness_days, evidence_map = await _gather_context(db, lead, tenant_id)
    evidence_ids = [uuid.UUID(e) for e in evidence_map.keys()]

    campaign_policy = (campaign.policy or {}) if campaign else {}
    allowed_channels = campaign_policy.get("allowed_channels") or ([] if campaign else ["email"])
    dry_run = campaign_policy.get("dry_run", True) if campaign else True

    dnc_match = await _dnc_matches(db, tenant_id, lead, contact, channel)
    consent_basis = await _consent_basis(db, tenant_id, contact)
    max_contact_per_day = campaign_policy.get("max_contact_per_day")
    freq_codes = await _frequency_exceeded(
        db, tenant_id, campaign, contact, lead, channel, max_contact_per_day
    )

    inp = policy_mod.PolicyInput(
        tenant_id=tenant_id,
        lead_id=lead.id,
        campaign_id=campaign.id if campaign else None,
        contact_id=contact.id if contact else None,
        channel=channel,
        lead_score=lead.score,
        qualification_status=lead.qualification_status,
        requires_qualification=campaign_policy.get("require_qualification", False),
        requires_evidence=campaign_policy.get("require_evidence", False),
        evidence_ids=evidence_ids,
        evidence_freshness_days=freshness_days,
        min_evidence_freshness_days=campaign_policy.get("min_evidence_freshness_days"),
        min_lead_score=campaign_policy.get("min_lead_score"),
        min_confidence=campaign_policy.get("min_confidence"),
        allowed_channels=allowed_channels,
        evidence_json=list(evidence_map.values()),
        outreach_enabled=settings.outreach_enabled,
        dry_run=dry_run,
        campaign_running=(campaign.status == "running") if campaign else True,
        dnc_matches=dnc_match,
        consent_basis=consent_basis,
        frequency_exceeded=bool(freq_codes),
        frequency_codes=freq_codes,
    )
    return inp, {"dry_run": dry_run}


async def _dnc_matches(db, tenant_id, lead, contact, channel) -> bool:
    stmt = select(DoNotContact).where(
        DoNotContact.tenant_id == tenant_id,
        (DoNotContact.expires_at.is_(None)) | (DoNotContact.expires_at > datetime.now(UTC)),
    )
    if contact is None:
        stmt = stmt.where(DoNotContact.contact_id.is_(None))
    rows = list((await db.execute(stmt)).scalars().all())
    for row in rows:
        if row.contact_id and contact and row.contact_id == contact.id:
            if row.channel is None or row.channel == channel:
                return True
        elif row.company_id and lead.company_id and row.company_id == lead.company_id:
            if row.channel is None or row.channel == channel:
                return True
    return False


async def _consent_basis(db, tenant_id, contact) -> str | None:
    if not contact:
        return None
    from app.models.do_not_contact import Consent

    result = await db.execute(
        select(Consent)
        .where(Consent.tenant_id == tenant_id, Consent.contact_id == contact.id)
        .order_by(Consent.recorded_at.desc())
        .limit(1)
    )
    consent = result.scalar_one_or_none()
    return consent.basis if consent else None


@router.post("/policies/evaluate", response_model=PolicyEvaluateResponse)
async def evaluate_policy(
    payload: PolicyEvaluateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> PolicyEvaluateResponse:
    await assert_lead_in_tenant(db, payload.lead_id, user.tenant_id)
    lead = await _get_owned_lead(db, payload.lead_id, user.tenant_id)

    campaign = None
    if payload.campaign_id:
        await assert_campaign_in_tenant(db, payload.campaign_id, user.tenant_id)
        campaign = await _get_entity(db, Campaign, payload.campaign_id)

    contact = None
    if payload.contact_id:
        await assert_contact_in_tenant(db, payload.contact_id, user.tenant_id)
        contact = await _get_entity(db, Contact, payload.contact_id)

    inp, _ = await _build_policy_input(db, lead, campaign, contact, payload.channel, user.tenant_id)
    decision, record = await evaluate_and_persist(
        db,
        lead=lead,
        campaign=campaign,
        contact=contact,
        channel=payload.channel,
        policy_input=inp,
        actor_user_id=user.id,
    )
    await db.flush()
    return PolicyEvaluateResponse(
        decision=decision.decision,
        policy_version=decision.policy_version,
        reasons=[
            {"code": r.code, "message": r.message, "severity": r.severity}
            for r in decision.reasons
        ],
        score=decision.score,
        evidence_ids=[str(e) for e in decision.evidence_ids],
        evaluated_at=decision.evaluated_at,
        lead_id=decision.lead_id,
        campaign_id=decision.campaign_id,
        contact_id=decision.contact_id,
        channel=decision.channel,
        decision_id=record.id,
    )


@router.get("/policy-decisions", response_model=list[PolicyDecisionRead])
async def list_policy_decisions(
    skip: int = 0,
    limit: int = 50,
    decision: str | None = None,
    lead_id: uuid.UUID | None = None,
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[PolicyDecision]:
    stmt = select(PolicyDecision).where(PolicyDecision.tenant_id == user.tenant_id)
    if decision:
        stmt = stmt.where(PolicyDecision.decision == decision)
    if lead_id:
        stmt = stmt.where(PolicyDecision.lead_id == lead_id)
    stmt = apply_sort(stmt, SORT_FIELDS, sort)
    stmt = paginate(stmt, skip, limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())