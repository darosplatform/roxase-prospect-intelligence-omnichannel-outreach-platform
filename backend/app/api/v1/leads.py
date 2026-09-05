import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.crud_helpers import apply_sort, paginate
from app.api.deps import get_current_active_user, require_role
from app.api.validators import (
    assert_company_in_tenant,
    assert_contact_in_tenant,
    assert_evidence_in_tenant,
)
from app.core.audit import record_audit
from app.core.metrics import metrics
from app.db.session import get_db
from app.models.lead import Lead
from app.models.user import User
from app.schemas.lead import (
    LeadCreate,
    LeadQualify,
    LeadRead,
    LeadScoreRead,
    LeadUpdate,
)
from app.services.scoring import assess_lead

router = APIRouter()

SORT_FIELDS = {
    "created_at": Lead.created_at,
    "updated_at": Lead.updated_at,
    "score": Lead.score,
}


async def _get_owned_lead(
    db: AsyncSession, lead_id: uuid.UUID, tenant_id: uuid.UUID
) -> Lead:
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.get("/leads", response_model=list[LeadRead])
async def list_leads(
    skip: int = 0,
    limit: int = 50,
    status: str | None = None,
    qual_status: str | None = None,
    company_id: uuid.UUID | None = None,
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[Lead]:
    stmt = select(Lead).where(Lead.tenant_id == user.tenant_id)
    if status:
        stmt = stmt.where(Lead.status == status)
    if qual_status:
        stmt = stmt.where(Lead.qualification_status == qual_status)
    if company_id:
        stmt = stmt.where(Lead.company_id == company_id)
    stmt = apply_sort(stmt, SORT_FIELDS, sort)
    stmt = paginate(stmt, skip, limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/leads", response_model=LeadRead, status_code=201)
async def create_lead(
    payload: LeadCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> Lead:
    data = payload.model_dump(exclude_unset=True)
    await assert_company_in_tenant(db, data.get("company_id"), user.tenant_id)
    await assert_contact_in_tenant(db, data.get("contact_id"), user.tenant_id)
    lead = Lead(**data, tenant_id=user.tenant_id)
    db.add(lead)
    await db.flush()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="lead.created",
        entity_type="lead",
        entity_id=lead.id,
    )
    await db.refresh(lead)
    metrics.inc("leads_created_total")
    return lead


@router.get("/leads/{lead_id}", response_model=LeadRead)
async def get_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Lead:
    return await _get_owned_lead(db, lead_id, user.tenant_id)


@router.patch("/leads/{lead_id}", response_model=LeadRead)
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> Lead:
    lead = await _get_owned_lead(db, lead_id, user.tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(lead, field, value)
    await db.flush()
    await db.refresh(lead)
    return lead


@router.post("/leads/{lead_id}/qualify", response_model=LeadRead)
async def qualify_lead(
    lead_id: uuid.UUID,
    payload: LeadQualify,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager", "analyst")),
) -> Lead:
    lead = await _get_owned_lead(db, lead_id, user.tenant_id)

    # A qualification must be grounded in evidence, never a bare number.
    if not payload.evidence_ids:
        raise HTTPException(
            status_code=422,
            detail="Qualification requires at least one evidence reference",
        )
    for evidence_id in payload.evidence_ids:
        await assert_evidence_in_tenant(db, evidence_id, user.tenant_id)

    old_status = lead.qualification_status
    lead.qualification_status = payload.status
    lead.qualified_at = datetime.now(UTC)
    lead.qualified_by = user.id
    if payload.reason is not None:
        lead.qualification_reason = payload.reason

    action = (
        "lead.disqualified"
        if payload.status == "disqualified"
        else f"lead.{payload.status}"
    )
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action=action,
        entity_type="lead",
        entity_id=lead.id,
        metadata={
            "from": old_status,
            "to": payload.status,
            "evidence_ids": [str(e) for e in payload.evidence_ids],
        },
    )
    await db.flush()
    await db.refresh(lead)
    if payload.status == "qualified":
        metrics.inc("leads_qualified_total")
    return lead


def _to_score_read(result) -> LeadScoreRead:
    return LeadScoreRead(
        score=result.score,
        scoring_version=result.version,
        breakdown={
            "fit": result.fit,
            "intent": result.intent,
            "signal": result.signal,
            "data_confidence": result.data_confidence,
            "freshness": result.freshness,
        },
        factors=[
            {
                "name": f.name,
                "impact": f.impact,
                "evidence_ids": f.evidence_ids,
            }
            for f in result.factors
        ],
        computed_at=result.computed_at,
    )


@router.post("/leads/{lead_id}/score", response_model=LeadScoreRead)
async def compute_lead_score(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager", "analyst")),
) -> LeadScoreRead:
    lead = await _get_owned_lead(db, lead_id, user.tenant_id)
    result = await assess_lead(db, lead)
    recomputed = lead.score is not None

    lead.score = result.score
    lead.fit_score = result.fit
    lead.intent_score = result.intent
    lead.signal_score = result.signal
    lead.data_confidence = result.data_confidence
    lead.freshness_score = result.freshness
    lead.scoring_version = result.version
    lead.score_explanation = result.to_dict()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="lead.score_recalculated" if recomputed else "lead.score_calculated",
        entity_type="lead",
        entity_id=lead.id,
        metadata={"score": result.score, "version": result.version},
    )
    await db.flush()
    return _to_score_read(result)


@router.get("/leads/{lead_id}/score", response_model=LeadScoreRead)
async def get_lead_score(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> LeadScoreRead:
    lead = await _get_owned_lead(db, lead_id, user.tenant_id)
    result = await assess_lead(db, lead)
    return _to_score_read(result)