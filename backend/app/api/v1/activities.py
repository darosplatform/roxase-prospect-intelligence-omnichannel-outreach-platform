from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.crud_helpers import paginate
from app.api.deps import get_current_active_user, require_role
from app.api.validators import (
    assert_company_in_tenant,
    assert_contact_in_tenant,
    assert_opportunity_in_tenant,
    assert_user_in_tenant,
)
from app.core.audit import record_audit
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
        paginate(
            select(Activity).where(Activity.tenant_id == user.tenant_id),
            skip,
            limit,
        )
    )
    return list(result.scalars().all())


@router.post("/activities", response_model=ActivityRead, status_code=201)
async def create_activity(
    payload: ActivityCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager", "operator")),
) -> Activity:
    data = payload.model_dump()
    await assert_company_in_tenant(db, data.get("company_id"), user.tenant_id)
    await assert_contact_in_tenant(db, data.get("contact_id"), user.tenant_id)
    await assert_opportunity_in_tenant(db, data.get("opportunity_id"), user.tenant_id)
    await assert_user_in_tenant(db, data.get("user_id"), user.tenant_id)

    activity = Activity(**data, tenant_id=user.tenant_id)
    db.add(activity)
    await db.flush()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="activity.created",
        entity_type="activity",
        entity_id=activity.id,
        metadata={"activity_type": activity.activity_type},
    )
    await db.refresh(activity)
    return activity