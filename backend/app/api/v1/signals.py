import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.crud_helpers import apply_sort, paginate, prepare_search
from app.api.deps import get_current_active_user, require_role
from app.api.validators import assert_company_in_tenant, assert_evidence_in_tenant
from app.core.audit import record_audit
from app.db.session import get_db
from app.models.signal import Signal
from app.models.user import User
from app.schemas.signal import SignalCreate, SignalRead
from app.services.signal_detection import signal_fingerprint

router = APIRouter()

SORT_FIELDS = {"created_at": Signal.created_at, "detected_at": Signal.detected_at}


@router.get("/signals", response_model=list[SignalRead])
async def list_signals(
    skip: int = 0,
    limit: int = 50,
    q: str | None = None,
    signal_type: str | None = None,
    status: str | None = None,
    company_id: uuid.UUID | None = None,
    detected_from: datetime | None = None,
    detected_to: datetime | None = None,
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[Signal]:
    stmt = select(Signal).where(
        Signal.tenant_id == user.tenant_id, Signal.deleted_at.is_(None)
    )
    if q:
        stmt = prepare_search(
            stmt, [Signal.title, Signal.description, Signal.source_name], q
        )
    if signal_type:
        stmt = stmt.where(Signal.signal_type == signal_type)
    if status:
        stmt = stmt.where(Signal.status == status)
    if company_id:
        stmt = stmt.where(Signal.company_id == company_id)
    if detected_from:
        stmt = stmt.where(Signal.detected_at >= detected_from)
    if detected_to:
        stmt = stmt.where(Signal.detected_at <= detected_to)
    stmt = apply_sort(stmt, SORT_FIELDS, sort)
    stmt = paginate(stmt, skip, limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/signals", response_model=SignalRead, status_code=201)
async def create_signal(
    payload: SignalCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> Signal:
    await assert_company_in_tenant(db, payload.company_id, user.tenant_id)
    if payload.evidence_id:
        await assert_evidence_in_tenant(db, payload.evidence_id, user.tenant_id)

    data = payload.model_dump()
    fp = signal_fingerprint(
        user.tenant_id,
        signal_type=data.get("signal_type"),
        company_id=data.get("company_id"),
        source_url=data.get("source_url"),
        source_name=data.get("source_name"),
    )
    existing = await db.execute(
        select(Signal).where(
            Signal.tenant_id == user.tenant_id,
            Signal.fingerprint == fp,
            Signal.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Duplicate signal")

    signal = Signal(**data, tenant_id=user.tenant_id, fingerprint=fp)
    db.add(signal)
    await db.flush()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="signal.created",
        entity_type="signal",
        entity_id=signal.id,
        metadata={"signal_type": signal.signal_type},
    )
    await db.refresh(signal)
    return signal


async def _get_owned_signal(
    db: AsyncSession, signal_id: uuid.UUID, tenant_id: uuid.UUID
) -> Signal:
    result = await db.execute(
        select(Signal).where(
            Signal.id == signal_id,
            Signal.tenant_id == tenant_id,
            Signal.deleted_at.is_(None),
        )
    )
    signal = result.scalar_one_or_none()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal


@router.get("/signals/{signal_id}", response_model=SignalRead)
async def get_signal(
    signal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Signal:
    return await _get_owned_signal(db, signal_id, user.tenant_id)


@router.delete("/signals/{signal_id}", status_code=204)
async def delete_signal(
    signal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> None:
    signal = await _get_owned_signal(db, signal_id, user.tenant_id)
    signal.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="signal.deleted",
        entity_type="signal",
        entity_id=signal.id,
    )
    await db.flush()