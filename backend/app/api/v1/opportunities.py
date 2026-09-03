import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.company import Company
from app.models.lead import Lead
from app.models.opportunity import Opportunity
from app.models.user import User
from app.schemas.opportunity import OpportunityCreate, OpportunityRead

router = APIRouter()


async def _validate_relations(
    db: AsyncSession, payload: dict, tenant_id: uuid.UUID, exclude: set[str] | None = None
):
    exclude = exclude or set()
    if "company_id" in payload and payload["company_id"] and "company_id" not in exclude:
        company = await db.execute(
            select(Company).where(
                Company.id == payload["company_id"], Company.tenant_id == tenant_id
            )
        )
        if company.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Company not found")
    if "lead_id" in payload and payload["lead_id"] and "lead_id" not in exclude:
        lead = await db.execute(
            select(Lead).where(Lead.id == payload["lead_id"], Lead.tenant_id == tenant_id)
        )
        if lead.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Lead not found")


@router.get("/opportunities", response_model=list[OpportunityRead])
async def list_opportunities(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[Opportunity]:
    result = await db.execute(
        select(Opportunity)
        .where(Opportunity.tenant_id == user.tenant_id)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


@router.post("/opportunities", response_model=OpportunityRead, status_code=201)
async def create_opportunity(
    payload: OpportunityCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Opportunity:
    data = payload.model_dump()
    await _validate_relations(db, data, user.tenant_id)
    opportunity = Opportunity(**data, tenant_id=user.tenant_id)
    db.add(opportunity)
    await db.flush()
    await db.refresh(opportunity)
    return opportunity


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityRead)
async def get_opportunity(
    opportunity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Opportunity:
    result = await db.execute(
        select(Opportunity).where(
            Opportunity.id == opportunity_id,
            Opportunity.tenant_id == user.tenant_id,
        )
    )
    opportunity = result.scalar_one_or_none()
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opportunity