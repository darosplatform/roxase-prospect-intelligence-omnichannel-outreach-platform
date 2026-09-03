import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.crud_helpers import apply_sort, paginate
from app.api.deps import get_current_active_user, require_role
from app.core.audit import record_audit
from app.db.session import get_db
from app.models.message_template import MessageTemplate
from app.models.user import User
from app.schemas.message_template import MessageTemplateCreate, MessageTemplateRead

router = APIRouter()

SORT_FIELDS = {"created_at": MessageTemplate.created_at, "name": MessageTemplate.name}


@router.get("/templates", response_model=list[MessageTemplateRead])
async def list_templates(
    skip: int = 0,
    limit: int = 50,
    channel: str | None = None,
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[MessageTemplate]:
    stmt = select(MessageTemplate).where(MessageTemplate.tenant_id == user.tenant_id)
    if channel:
        stmt = stmt.where(MessageTemplate.channel == channel)
    stmt = apply_sort(stmt, SORT_FIELDS, sort)
    stmt = paginate(stmt, skip, limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/templates", response_model=MessageTemplateRead, status_code=201)
async def create_template(
    payload: MessageTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager")),
) -> MessageTemplate:
    template = MessageTemplate(**payload.model_dump(), tenant_id=user.tenant_id)
    db.add(template)
    await db.flush()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="template.created",
        entity_type="message_template",
        entity_id=template.id,
        metadata={"channel": template.channel},
    )
    await db.refresh(template)
    return template


@router.get("/templates/{template_id}", response_model=MessageTemplateRead)
async def get_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> MessageTemplate:
    result = await db.execute(
        select(MessageTemplate).where(
            MessageTemplate.id == template_id,
            MessageTemplate.tenant_id == user.tenant_id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template