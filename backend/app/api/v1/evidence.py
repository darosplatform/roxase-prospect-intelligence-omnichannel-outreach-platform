import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.crud_helpers import apply_sort, paginate
from app.api.deps import get_current_active_user, require_role
from app.api.validators import (
    assert_company_in_tenant,
    assert_contact_in_tenant,
    assert_lead_in_tenant,
)
from app.core.audit import record_audit
from app.db.session import get_db
from app.models.evidence import Evidence
from app.models.user import User
from app.schemas.evidence import EvidenceCreate, EvidenceRead
from app.schemas.signal import SignalRead
from app.services.signal_detection import ingest_evidence

router = APIRouter()

SORT_FIELDS = {
    "created_at": Evidence.created_at,
    "collected_at": Evidence.collected_at,
    "published_at": Evidence.published_at,
    "confidence": Evidence.confidence,
}


async def _validate_relations(
    db: AsyncSession, data: dict, tenant_id: uuid.UUID
) -> None:
    await assert_company_in_tenant(db, data.get("company_id"), tenant_id)
    await assert_contact_in_tenant(db, data.get("contact_id"), tenant_id)
    await assert_lead_in_tenant(db, data.get("lead_id"), tenant_id)


@router.get("/evidence", response_model=list[EvidenceRead])
async def list_evidence(
    skip: int = 0,
    limit: int = 50,
    evidence_type: str | None = None,
    company_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[Evidence]:
    stmt = select(Evidence).where(Evidence.tenant_id == user.tenant_id)
    if evidence_type:
        stmt = stmt.where(Evidence.evidence_type == evidence_type)
    if company_id:
        stmt = stmt.where(Evidence.company_id == company_id)
    if lead_id:
        stmt = stmt.where(Evidence.lead_id == lead_id)
    stmt = apply_sort(stmt, SORT_FIELDS, sort)
    stmt = paginate(stmt, skip, limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/evidence", response_model=EvidenceRead, status_code=201)
async def create_evidence(
    payload: EvidenceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> Evidence:
    data = payload.model_dump(exclude_unset=True)
    await _validate_relations(db, data, user.tenant_id)
    if "metadata" in data:
        data["evidence_metadata"] = data.pop("metadata")

    evidence = Evidence(**data, tenant_id=user.tenant_id)
    db.add(evidence)
    await db.flush()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="evidence.created",
        entity_type="evidence",
        entity_id=evidence.id,
        metadata={"evidence_type": evidence.evidence_type},
    )
    await db.refresh(evidence)
    return evidence


async def _get_owned_evidence(
    db: AsyncSession, evidence_id: uuid.UUID, tenant_id: uuid.UUID
) -> Evidence:
    result = await db.execute(
        select(Evidence).where(Evidence.id == evidence_id, Evidence.tenant_id == tenant_id)
    )
    evidence = result.scalar_one_or_none()
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return evidence


@router.post("/evidence/{evidence_id}/detect-signal", response_model=SignalRead | None)
async def detect_evidence_signal(
    evidence_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
):
    """Signal Intelligence (C4): run the deterministic keyword/evidence_type
    classifier against this Evidence. Returns null when there is no support
    for any signal (nothing is ever fabricated) — that is a normal, valid
    outcome, not an error. Idempotent: re-running against the same evidence
    returns the same already-created Signal rather than duplicating it.
    """
    evidence = await _get_owned_evidence(db, evidence_id, user.tenant_id)
    signal = await ingest_evidence(db, user.tenant_id, evidence)
    await db.commit()
    return signal