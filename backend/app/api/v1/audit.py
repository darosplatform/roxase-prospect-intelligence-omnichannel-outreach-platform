"""Read-only audit trail API.

AuditEvent rows are already written throughout the app via
`app.core.audit.record_audit`; this router only exposes them (list, filtered,
paginated, tenant-scoped) — it never writes. Needed for the frontend's Audit
view (actor, action, timestamp, entity).
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.crud_helpers import paginate
from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.audit import AuditEvent
from app.models.user import User
from app.schemas.audit import AuditEventRead

router = APIRouter()


@router.get("/audit", response_model=list[AuditEventRead])
async def list_audit_events(
    skip: int = 0,
    limit: int = 50,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[AuditEvent]:
    stmt = select(AuditEvent).where(AuditEvent.tenant_id == user.tenant_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    if created_from:
        stmt = stmt.where(AuditEvent.created_at >= created_from)
    if created_to:
        stmt = stmt.where(AuditEvent.created_at <= created_to)
    stmt = stmt.order_by(AuditEvent.created_at.desc())
    stmt = paginate(stmt, skip, limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
