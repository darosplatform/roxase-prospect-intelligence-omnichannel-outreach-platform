import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.crud_helpers import apply_sort, paginate, prepare_search
from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.contact import Contact
from app.models.user import User
from app.schemas.contact import ContactCreate, ContactRead

router = APIRouter()

SORT_FIELDS = {
    "created_at": Contact.created_at,
    "updated_at": Contact.updated_at,
    "first_name": Contact.first_name,
    "last_name": Contact.last_name,
}


@router.get("/contacts", response_model=list[ContactRead])
async def list_contacts(
    skip: int = 0,
    limit: int = 50,
    q: str | None = None,
    company_id: uuid.UUID | None = None,
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[Contact]:
    stmt = select(Contact).where(Contact.tenant_id == user.tenant_id)
    if company_id:
        stmt = stmt.where(Contact.company_id == company_id)
    stmt = prepare_search(
        stmt,
        [Contact.first_name, Contact.last_name, Contact.email, Contact.job_title],
        q,
    )
    stmt = apply_sort(stmt, SORT_FIELDS, sort)
    stmt = paginate(stmt, skip, limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/contacts/{contact_id}", response_model=ContactRead)
async def get_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Contact:
    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id, Contact.tenant_id == user.tenant_id
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.post("/contacts", response_model=ContactRead, status_code=201)
async def create_contact(
    payload: ContactCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Contact:
    contact = Contact(**payload.model_dump(), tenant_id=user.tenant_id)
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    return contact
