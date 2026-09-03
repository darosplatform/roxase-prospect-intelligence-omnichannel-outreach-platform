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
    assert_lead_in_tenant,
    assert_user_in_tenant,
)
from app.core.audit import record_audit
from app.db.session import get_db
from app.models.opportunity import Opportunity
from app.models.user import User
from app.schemas.opportunity import OpportunityCreate, OpportunityRead, OpportunityUpdate

router = APIRouter()

SORT_FIELDS = {
    "created_at": Opportunity.created_at,
    "updated_at": Opportunity.updated_at,
    "value": Opportunity.value,
    "probability": Opportunity.probability,
}


async def _validate_relations(
    db: AsyncSession, payload: dict, tenant_id: uuid.UUID, exclude: set[str] | None = None
):
    exclude = exclude or set()
    if "company_id" not in exclude:
        await assert_company_in_tenant(db, payload.get("company_id"), tenant_id)
    if "contact_id" not in exclude:
        await assert_contact_in_tenant(db, payload.get("contact_id"), tenant_id)
    if "lead_id" not in exclude:
        await assert_lead_in_tenant(db, payload.get("lead_id"), tenant_id)
    if "owner_user_id" not in exclude:
        await assert_user_in_tenant(db, payload.get("owner_user_id"), tenant_id)


async def _get_owned_opportunity(
    db: AsyncSession, opportunity_id: uuid.UUID, tenant_id: uuid.UUID
) -> Opportunity:
    result = await db.execute(
        select(Opportunity).where(
            Opportunity.id == opportunity_id,
            Opportunity.tenant_id == tenant_id,
            Opportunity.deleted_at.is_(None),
        )
    )
    opportunity = result.scalar_one_or_none()
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opportunity


@router.get("/opportunities", response_model=list[OpportunityRead])
async def list_opportunities(
    skip: int = 0,
    limit: int = 50,
    stage: str | None = None,
    company_id: uuid.UUID | None = None,
    owner_user_id: uuid.UUID | None = None,
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[Opportunity]:
    stmt = select(Opportunity).where(
        Opportunity.tenant_id == user.tenant_id, Opportunity.deleted_at.is_(None)
    )
    if stage:
        stmt = stmt.where(Opportunity.stage == stage)
    if company_id:
        stmt = stmt.where(Opportunity.company_id == company_id)
    if owner_user_id:
        stmt = stmt.where(Opportunity.owner_user_id == owner_user_id)
    stmt = apply_sort(stmt, SORT_FIELDS, sort)
    stmt = paginate(stmt, skip, limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "/opportunities", response_model=OpportunityRead, status_code=201
)
async def create_opportunity(
    payload: OpportunityCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> Opportunity:
    data = payload.model_dump()
    await _validate_relations(db, data, user.tenant_id)
    opportunity = Opportunity(**data, tenant_id=user.tenant_id)
    db.add(opportunity)
    await db.flush()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="opportunity.created",
        entity_type="opportunity",
        entity_id=opportunity.id,
    )
    await db.refresh(opportunity)
    return opportunity


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityRead)
async def get_opportunity(
    opportunity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Opportunity:
    return await _get_owned_opportunity(db, opportunity_id, user.tenant_id)


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityRead)
async def update_opportunity(
    opportunity_id: uuid.UUID,
    payload: OpportunityUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> Opportunity:
    opportunity = await _get_owned_opportunity(db, opportunity_id, user.tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    await _validate_relations(db, updates, user.tenant_id)
    old_stage = opportunity.stage
    for field, value in updates.items():
        setattr(opportunity, field, value)
    if "stage" in updates and updates["stage"] != old_stage:
        await record_audit(
            db,
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            action="opportunity.stage_changed",
            entity_type="opportunity",
            entity_id=opportunity.id,
            metadata={"from": old_stage, "to": opportunity.stage},
        )
    await db.flush()
    await db.refresh(opportunity)
    return opportunity


@router.delete("/opportunities/{opportunity_id}", status_code=204)
async def delete_opportunity(
    opportunity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> None:
    opportunity = await _get_owned_opportunity(db, opportunity_id, user.tenant_id)
    opportunity.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="opportunity.deleted",
        entity_type="opportunity",
        entity_id=opportunity.id,
    )
    await db.flush()