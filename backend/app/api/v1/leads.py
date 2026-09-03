from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.lead import Lead
from app.models.user import User
from app.schemas.lead import LeadCreate, LeadRead

router = APIRouter()


@router.get("/leads", response_model=list[LeadRead])
async def list_leads(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[Lead]:
    result = await db.execute(
        select(Lead)
        .where(Lead.tenant_id == user.tenant_id)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


@router.post("/leads", response_model=LeadRead, status_code=201)
async def create_lead(
    payload: LeadCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Lead:
    lead = Lead(**payload.model_dump(), tenant_id=user.tenant_id)
    db.add(lead)
    await db.flush()
    await db.refresh(lead)
    return lead
