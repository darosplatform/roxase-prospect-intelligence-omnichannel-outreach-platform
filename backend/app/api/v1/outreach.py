import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.crud_helpers import apply_sort, paginate
from app.api.deps import get_current_active_user, require_role
from app.api.v1.policies import _build_policy_input
from app.api.validators import (
    assert_campaign_in_tenant,
    assert_contact_in_tenant,
    assert_template_in_tenant,
)
from app.core.audit import record_audit
from app.db.session import get_db
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.lead import Lead
from app.models.outreach_request import OutreachRequest
from app.models.user import User
from app.schemas.outreach_request import (
    OutreachRequestCreate,
    OutreachRequestRead,
)
from app.services.outreach import (
    dispatch_request,
    find_by_idempotency,
    make_idempotency_key,
)

router = APIRouter()

SORT_FIELDS = {"created_at": OutreachRequest.created_at, "status": OutreachRequest.status}


async def _get_owned_request(db, req_id: uuid.UUID, tenant_id) -> OutreachRequest:
    result = await db.execute(
        select(OutreachRequest).where(
            OutreachRequest.id == req_id, OutreachRequest.tenant_id == tenant_id
        )
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="OutreachRequest not found")
    return req


async def _get_entity(db, model, entity_id: uuid.UUID):
    result = await db.execute(select(model).where(model.id == entity_id))
    return result.scalar_one_or_none()


@router.get("/outreach", response_model=list[OutreachRequestRead])
async def list_outreach(
    skip: int = 0,
    limit: int = 50,
    status: str | None = None,
    channel: str | None = None,
    lead_id: uuid.UUID | None = None,
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[OutreachRequest]:
    stmt = select(OutreachRequest).where(OutreachRequest.tenant_id == user.tenant_id)
    if status:
        stmt = stmt.where(OutreachRequest.status == status)
    if channel:
        stmt = stmt.where(OutreachRequest.channel == channel)
    if lead_id:
        stmt = stmt.where(OutreachRequest.lead_id == lead_id)
    stmt = apply_sort(stmt, SORT_FIELDS, sort)
    stmt = paginate(stmt, skip, limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/outreach/{outreach_id}", response_model=OutreachRequestRead)
async def get_outreach(
    outreach_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> OutreachRequest:
    return await _get_owned_request(db, outreach_id, user.tenant_id)


@router.post("/outreach", response_model=OutreachRequestRead, status_code=201)
async def create_outreach_request(
    payload: OutreachRequestCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager", "operator")),
) -> OutreachRequest:
    lead_result = await db.execute(
        select(Lead)
        .where(Lead.company_id.isnot(None), Lead.tenant_id == user.tenant_id)
        .order_by(Lead.created_at.desc())
        .limit(1)
    )
    lead = lead_result.scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=422, detail="No lead available for outreach")

    contact = None
    if payload.contact_id:
        await assert_contact_in_tenant(db, payload.contact_id, user.tenant_id)
        contact = await _get_entity(db, Contact, payload.contact_id)

    campaign = None
    if payload.campaign_id:
        await assert_campaign_in_tenant(db, payload.campaign_id, user.tenant_id)
        campaign = await _get_entity(db, Campaign, payload.campaign_id)

    if payload.template_id:
        await assert_template_in_tenant(db, payload.template_id, user.tenant_id)

    channel = payload.channel or (campaign.channel if campaign else "email")
    idempotency_key = make_idempotency_key(
        user.tenant_id,
        campaign.id if campaign else None,
        lead.id,
        contact.id if contact else None,
        channel,
        payload.template_id,
        "default-send",
    )

    existing = await find_by_idempotency(db, user.tenant_id, idempotency_key)
    if existing is not None:
        return existing

    inp, _ = await _build_policy_input(db, lead, campaign, contact, channel, user.tenant_id)
    decision, record = await _evaluate(db, lead, campaign, contact, channel, inp, user.id)

    if decision.decision == "DENY":
        await record_audit(
            db,
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            action="outreach.denied",
            entity_type="outreach_request",
            metadata={
                "lead_id": str(lead.id),
                "campaign_id": str(campaign.id) if campaign else None,
                "reason_codes": [r.code for r in decision.reasons],
            },
        )
        req = OutreachRequest(
            tenant_id=user.tenant_id,
            campaign_id=campaign.id if campaign else None,
            lead_id=lead.id,
            contact_id=contact.id if contact else None,
            template_id=payload.template_id,
            policy_decision_id=record.id,
            channel=channel,
            status="denied",
            idempotency_key=idempotency_key,
            scheduled_at=payload.scheduled_at,
        )
        db.add(req)
        await db.flush()
        await db.refresh(req)
        return req

    # A REVIEW needs human judgement; leave the request pending for a review path.
    initial_status = "approved" if decision.decision == "ALLOW" else "pending"

    req = OutreachRequest(
        tenant_id=user.tenant_id,
        campaign_id=campaign.id if campaign else None,
        lead_id=lead.id,
        contact_id=contact.id if contact else None,
        template_id=payload.template_id,
        policy_decision_id=record.id,
        channel=channel,
        status=initial_status,
        idempotency_key=idempotency_key,
        scheduled_at=payload.scheduled_at,
    )
    db.add(req)
    if initial_status == "approved":
        await record_audit(
            db,
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            action="outreach.approved",
            entity_type="outreach_request",
            entity_id=req.id,
            metadata={"channel": channel},
        )
    await db.flush()
    await db.refresh(req)
    return req


async def _evaluate(db, lead, campaign, contact, channel, inp, actor_user_id):
    from app.services.outreach import evaluate_and_persist

    decision, record = await evaluate_and_persist(
        db,
        lead=lead,
        campaign=campaign,
        contact=contact,
        channel=channel,
        policy_input=inp,
        actor_user_id=actor_user_id,
    )
    return decision, record


@router.post("/outreach/{outreach_id}/approve", response_model=OutreachRequestRead)
async def approve_outreach(
    outreach_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> OutreachRequest:
    req = await _get_owned_request(db, outreach_id, user.tenant_id)
    if req.status == "denied":
        raise HTTPException(status_code=409, detail="Denied request cannot be approved")
    if req.status in ("sent", "delivered", "failed", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Cannot approve status '{req.status}'")
    if req.status != "approved":
        req.status = "approved"
        await record_audit(
            db,
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            action="outreach.approved",
            entity_type="outreach_request",
            entity_id=req.id,
            metadata={"channel": req.channel},
        )
    await db.flush()
    await db.refresh(req)
    return req


@router.post("/outreach/{outreach_id}/dispatch", response_model=OutreachRequestRead)
async def dispatch_outreach(
    outreach_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager", "operator")),
) -> OutreachRequest:
    req = await _get_owned_request(db, outreach_id, user.tenant_id)
    if req.status == "denied":
        raise HTTPException(status_code=409, detail="Denied request cannot be dispatched")
    campaign = None
    if req.campaign_id:
        campaign = await _get_entity(db, Campaign, req.campaign_id)
    dry_run = (campaign.policy or {}).get("dry_run", True) if campaign else True
    return await dispatch_request(db, req, dry_run=dry_run)


@router.post("/outreach/{outreach_id}/cancel", response_model=OutreachRequestRead)
async def cancel_outreach(
    outreach_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> OutreachRequest:
    req = await _get_owned_request(db, outreach_id, user.tenant_id)
    if req.status in ("sent", "delivered", "failed", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Cannot cancel status '{req.status}'")
    req.status = "cancelled"
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="outreach.cancelled",
        entity_type="outreach_request",
        entity_id=req.id,
    )
    await db.flush()
    await db.refresh(req)
    return req