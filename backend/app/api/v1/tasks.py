import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.crud_helpers import apply_sort, paginate
from app.api.deps import get_current_active_user, require_role
from app.api.validators import (
    assert_company_in_tenant,
    assert_contact_in_tenant,
    assert_opportunity_in_tenant,
    assert_user_in_tenant,
)
from app.core.audit import record_audit
from app.db.session import get_db
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate

router = APIRouter()

SORT_FIELDS = {"created_at": Task.created_at, "updated_at": Task.updated_at, "due_at": Task.due_at}


async def _get_owned_task(
    db: AsyncSession, task_id: uuid.UUID, tenant_id: uuid.UUID
) -> Task:
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.tenant_id == tenant_id,
            Task.deleted_at.is_(None),
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


async def _validate_relations(db: AsyncSession, payload: dict, tenant_id: uuid.UUID):
    await assert_company_in_tenant(db, payload.get("company_id"), tenant_id)
    await assert_contact_in_tenant(db, payload.get("contact_id"), tenant_id)
    await assert_opportunity_in_tenant(db, payload.get("opportunity_id"), tenant_id)
    await assert_user_in_tenant(db, payload.get("assigned_to"), tenant_id)


@router.get("/tasks", response_model=list[TaskRead])
async def list_tasks(
    skip: int = 0,
    limit: int = 50,
    status: str | None = None,
    priority: str | None = None,
    assigned_to: uuid.UUID | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[Task]:
    stmt = select(Task).where(Task.tenant_id == user.tenant_id, Task.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Task.status == status)
    if priority:
        stmt = stmt.where(Task.priority == priority)
    if assigned_to:
        stmt = stmt.where(Task.assigned_to == assigned_to)
    if due_before:
        stmt = stmt.where(Task.due_at <= due_before)
    if due_after:
        stmt = stmt.where(Task.due_at >= due_after)
    stmt = apply_sort(stmt, SORT_FIELDS, sort)
    stmt = paginate(stmt, skip, limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/tasks", response_model=TaskRead, status_code=201)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager", "operator")),
) -> Task:
    data = payload.model_dump()
    await _validate_relations(db, data, user.tenant_id)
    task = Task(**data, tenant_id=user.tenant_id)
    db.add(task)
    await db.flush()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="task.created",
        entity_type="task",
        entity_id=task.id,
    )
    await db.refresh(task)
    return task


@router.patch("/tasks/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager", "operator")),
) -> Task:
    task = await _get_owned_task(db, task_id, user.tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    await _validate_relations(db, updates, user.tenant_id)
    for field, value in updates.items():
        setattr(task, field, value)
    if updates.get("status") == "done" and task.completed_at is None:
        task.completed_at = datetime.now(UTC)
        await record_audit(
            db,
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            action="task.completed",
            entity_type="task",
            entity_id=task.id,
        )
    elif updates.get("status") and updates["status"] != "done":
        task.completed_at = None
    await db.flush()
    await db.refresh(task)
    return task


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("owner", "admin", "manager", "operator")),
) -> None:
    task = await _get_owned_task(db, task_id, user.tenant_id)
    task.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="task.deleted",
        entity_type="task",
        entity_id=task.id,
    )
    await db.flush()