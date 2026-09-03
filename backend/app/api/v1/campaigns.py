import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.campaign import Campaign
from app.models.user import User
from app.schemas.campaign import CampaignCreate, CampaignRead, CampaignUpdate

router = APIRouter()


async def _get_owned_campaign(
    db: AsyncSession, campaign_id: uuid.UUID, tenant_id: uuid.UUID
) -> Campaign:
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.get("/campaigns", response_model=list[CampaignRead])
async def list_campaigns(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[Campaign]:
    result = await db.execute(
        select(Campaign).where(Campaign.tenant_id == user.tenant_id).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


@router.post("/campaigns", response_model=CampaignRead, status_code=201)
async def create_campaign(
    payload: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Campaign:
    campaign = Campaign(**payload.model_dump(), tenant_id=user.tenant_id, created_by=user.id)
    db.add(campaign)
    await db.flush()
    await db.refresh(campaign)
    return campaign


@router.get("/campaigns/{campaign_id}", response_model=CampaignRead)
async def get_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Campaign:
    return await _get_owned_campaign(db, campaign_id, user.tenant_id)


@router.patch("/campaigns/{campaign_id}", response_model=CampaignRead)
async def update_campaign(
    campaign_id: uuid.UUID,
    payload: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Campaign:
    campaign = await _get_owned_campaign(db, campaign_id, user.tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(campaign, field, value)
    await db.flush()
    await db.refresh(campaign)
    return campaign