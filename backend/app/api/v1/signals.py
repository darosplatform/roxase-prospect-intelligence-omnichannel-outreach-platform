import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.company import Company
from app.models.signal import Signal
from app.models.user import User
from app.schemas.signal import SignalCreate, SignalRead

router = APIRouter()


async def _assert_company_in_tenant(db: AsyncSession, company_id: uuid.UUID, tenant_id: uuid.UUID):
    result = await db.execute(
        select(Company).where(Company.id == company_id, Company.tenant_id == tenant_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Company not found")


@router.get("/signals", response_model=list[SignalRead])
async def list_signals(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[Signal]:
    result = await db.execute(
        select(Signal)
        .where(Signal.tenant_id == user.tenant_id)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


@router.post("/signals", response_model=SignalRead, status_code=201)
async def create_signal(
    payload: SignalCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Signal:
    await _assert_company_in_tenant(db, payload.company_id, user.tenant_id)
    data = payload.model_dump()
    signal = Signal(**data, tenant_id=user.tenant_id)
    db.add(signal)
    await db.flush()
    await db.refresh(signal)
    return signal