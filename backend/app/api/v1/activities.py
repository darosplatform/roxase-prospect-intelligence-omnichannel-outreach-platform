from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.activity import Activity
from app.models.user import User
from app.schemas.activity import ActivityCreate, ActivityRead

router = APIRouter()


@router.get("/activities", response_model=list[ActivityRead])
async def list_activities(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[Activity]:
    result = await db.execute(
        select(Activity)
        .where(Activity.tenant_id == user.tenant_id)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


@router.post("/activities", response_model=ActivityRead, status_code=201)
async def create_activity(
    payload: ActivityCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Activity:
    data = payload.model_dump()
    activity = Activity(**data, tenant_id=user.tenant_id)
    db.add(activity)
    await db.flush()
    await db.refresh(activity)
    return activity