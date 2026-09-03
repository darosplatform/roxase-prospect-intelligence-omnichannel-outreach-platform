import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.crud_helpers import apply_sort, paginate
from app.api.deps import get_current_active_user, require_role
from app.core.audit import record_audit
from app.db.session import get_db
from app.models.campaign import Campaign
from app.models.user import User
from app.schemas.campaign import CampaignCreate, CampaignRead, CampaignUpdate

router = APIRouter()

SORT_FIELDS = {"created_at": Campaign.created_at, "updated_at": Campaign.updated_at}


async def _get_owned_campaign(
    db: AsyncSession, campaign_id: uuid.UUID, tenant_id: uuid.UUID
) -> Campaign:
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.tenant_id == tenant_id,
            Campaign.deleted_at.is_(None),
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.get("/campaigns", response_model=list[CampaignRead])
async def list_campaigns(
    skip: int = 0,
    limit: int = 50,
    status: str | None = None,
    channel: str | None = None,
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[Campaign]:
    stmt = select(Campaign).where(
        Campaign.tenant_id == user.tenant_id, Campaign.deleted_at.is_(None)
    )
    if status:
        stmt = stmt.where(Campaign.status == status)
    if channel:
        stmt = stmt.where(Campaign.channel == channel)
    stmt = apply_sort(stmt, SORT_FIELDS, sort)
    stmt = paginate(stmt, skip, limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "/campaigns", response_model=CampaignRead, status_code=201
)
async def create_campaign(
    payload: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> Campaign:
    campaign = Campaign(**payload.model_dump(), tenant_id=user.tenant_id, created_by=user.id)
    db.add(campaign)
    await db.flush()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="campaign.created",
        entity_type="campaign",
        entity_id=campaign.id,
        metadata={"channel": campaign.channel},
    )
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
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> Campaign:
    campaign = await _get_owned_campaign(db, campaign_id, user.tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    old_status = campaign.status
    for field, value in updates.items():
        setattr(campaign, field, value)
    if "status" in updates and updates["status"] != old_status:
        await record_audit(
            db,
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            action="campaign.status_changed",
            entity_type="campaign",
            entity_id=campaign.id,
            metadata={"from": old_status, "to": campaign.status},
        )
    await db.flush()
    await db.refresh(campaign)
    return campaign


@router.delete("/campaigns/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> None:
    campaign = await _get_owned_campaign(db, campaign_id, user.tenant_id)
    campaign.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="campaign.deleted",
        entity_type="campaign",
        entity_id=campaign.id,
    )
    await db.flush()