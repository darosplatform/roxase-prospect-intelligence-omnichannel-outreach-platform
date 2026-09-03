import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.crud_helpers import apply_sort, paginate
from app.api.deps import get_current_active_user, require_role
from app.api.validators import assert_company_in_tenant, assert_contact_in_tenant
from app.core.audit import record_audit
from app.db.session import get_db
from app.models.do_not_contact import Consent, DoNotContact
from app.models.user import User
from app.schemas.do_not_contact import (
    ConsentCreate,
    DoNotContactCreate,
    DoNotContactRead,
)

router = APIRouter()

SORT_FIELDS = {"created_at": DoNotContact.created_at}


@router.get("/do-not-contact", response_model=list[DoNotContactRead])
async def list_dnc(
    skip: int = 0,
    limit: int = 50,
    channel: str | None = None,
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[DoNotContact]:
    stmt = select(DoNotContact).where(DoNotContact.tenant_id == user.tenant_id)
    if channel:
        stmt = stmt.where(DoNotContact.channel == channel)
    stmt = apply_sort(stmt, SORT_FIELDS, sort)
    stmt = paginate(stmt, skip, limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/do-not-contact", response_model=DoNotContactRead, status_code=201)
async def create_dnc(
    payload: DoNotContactCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> DoNotContact:
    data = payload.model_dump(exclude_unset=True)
    await assert_contact_in_tenant(db, data.get("contact_id"), user.tenant_id)
    await assert_company_in_tenant(db, data.get("company_id"), user.tenant_id)
    dnc = DoNotContact(**data, tenant_id=user.tenant_id, created_by=user.id)
    db.add(dnc)
    await db.flush()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="do_not_contact.created",
        entity_type="do_not_contact",
        entity_id=dnc.id,
    )
    await db.refresh(dnc)
    return dnc


@router.get("/do-not-contact/{dnc_id}", response_model=DoNotContactRead)
async def get_dnc(
    dnc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> DoNotContact:
    result = await db.execute(
        select(DoNotContact).where(
            DoNotContact.id == dnc_id, DoNotContact.tenant_id == user.tenant_id
        )
    )
    dnc = result.scalar_one_or_none()
    if not dnc:
        raise HTTPException(status_code=404, detail="DoNotContact not found")
    return dnc


@router.delete("/do-not-contact/{dnc_id}", status_code=204)
async def delete_dnc(
    dnc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> None:
    result = await db.execute(
        select(DoNotContact).where(
            DoNotContact.id == dnc_id, DoNotContact.tenant_id == user.tenant_id
        )
    )
    dnc = result.scalar_one_or_none()
    if not dnc:
        raise HTTPException(status_code=404, detail="DoNotContact not found")
    await db.delete(dnc)
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="do_not_contact.deleted",
        entity_type="do_not_contact",
        entity_id=dnc.id,
    )
    await db.flush()


@router.post("/consents", response_model=dict)
async def record_consent(
    payload: ConsentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> dict:
    await assert_contact_in_tenant(db, payload.contact_id, user.tenant_id)
    consent = Consent(
        tenant_id=user.tenant_id,
        contact_id=payload.contact_id,
        channel=payload.channel,
        basis=payload.basis,
        created_by=user.id,
    )
    db.add(consent)
    await db.flush()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="consent.recorded",
        entity_type="consent",
        entity_id=consent.id,
        metadata={"basis": consent.basis},
    )
    return {"id": str(consent.id), "basis": consent.basis, "contact_id": str(consent.contact_id)}