
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.crud_helpers import paginate
from app.api.deps import get_current_active_user, require_role
from app.api.validators import (
    assert_company_in_tenant,
    assert_contact_in_tenant,
    assert_opportunity_in_tenant,
)
from app.core.audit import record_audit
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
        paginate(
            select(Note).where(Note.tenant_id == user.tenant_id, Note.deleted_at.is_(None)),
            skip,
            limit,
        )
    )
    return list(result.scalars().all())


@router.post("/notes", response_model=NoteRead, status_code=201)
async def create_note(
    payload: NoteCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager", "operator")),
) -> Note:
    data = payload.model_dump()
    await assert_company_in_tenant(db, data.get("company_id"), user.tenant_id)
    await assert_contact_in_tenant(db, data.get("contact_id"), user.tenant_id)
    await assert_opportunity_in_tenant(db, data.get("opportunity_id"), user.tenant_id)

    note = Note(**data, tenant_id=user.tenant_id, author_user_id=user.id)
    db.add(note)
    await db.flush()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="note.created",
        entity_type="note",
        entity_id=note.id,
    )
    await db.refresh(note)
    return note


async def _get_owned_note(db: AsyncSession, note_id: uuid.UUID, tenant_id: uuid.UUID) -> Note:
    result = await db.execute(
        select(Note).where(
            Note.id == note_id,
            Note.tenant_id == tenant_id,
            Note.deleted_at.is_(None),
        )
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(
    note_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager", "operator")),
) -> None:
    note = await _get_owned_note(db, note_id, user.tenant_id)
    note.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="note.deleted",
        entity_type="note",
        entity_id=note.id,
    )
    await db.flush()