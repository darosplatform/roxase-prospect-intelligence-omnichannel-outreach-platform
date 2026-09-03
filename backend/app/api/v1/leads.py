from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.lead import Lead
from app.schemas.lead import LeadCreate, LeadRead

router = APIRouter()


@router.get("/leads", response_model=list[LeadRead])
async def list_leads(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[Lead]:
    result = await db.execute(select(Lead).offset(skip).limit(limit))
    return list(result.scalars().all())


@router.post("/leads", response_model=LeadRead, status_code=201)
async def create_lead(
    payload: LeadCreate,
    db: AsyncSession = Depends(get_db),
) -> Lead:
    lead = Lead(**payload.model_dump())
    db.add(lead)
    await db.flush()
    await db.refresh(lead)
    return lead
