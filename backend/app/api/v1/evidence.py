import uuid

from fastapi import APIRouter, Depends
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