from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.note import Note
from app.models.user import User
from app.schemas.note import NoteCreate, NoteRead

router = APIRouter()


@router.get("/notes", response_model=list[NoteRead])
async def list_notes(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[Note]:
    result = await db.execute(
        select(Note).where(Note.tenant_id == user.tenant_id).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


@router.post("/notes", response_model=NoteRead, status_code=201)
async def create_note(
    payload: NoteCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Note:
    note = Note(**payload.model_dump(), tenant_id=user.tenant_id, author_user_id=user.id)
    db.add(note)
    await db.flush()
    await db.refresh(note)
    return note