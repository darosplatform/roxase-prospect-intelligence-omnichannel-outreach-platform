from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.contact import Contact
from app.models.user import User
from app.schemas.contact import ContactCreate, ContactRead

router = APIRouter()


@router.get("/contacts", response_model=list[ContactRead])
async def list_contacts(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[Contact]:
    result = await db.execute(
        select(Contact)
        .where(Contact.tenant_id == user.tenant_id)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


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
