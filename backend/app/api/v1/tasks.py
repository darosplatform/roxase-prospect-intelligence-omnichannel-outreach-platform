import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate

router = APIRouter()


async def _get_owned_task(
    db: AsyncSession, task_id: uuid.UUID, tenant_id: uuid.UUID
) -> Task:
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.tenant_id == tenant_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/tasks", response_model=list[TaskRead])
async def list_tasks(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[Task]:
    result = await db.execute(
        select(Task).where(Task.tenant_id == user.tenant_id).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


@router.post("/tasks", response_model=TaskRead, status_code=201)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Task:
    task = Task(**payload.model_dump(), tenant_id=user.tenant_id)
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


@router.patch("/tasks/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Task:
    task = await _get_owned_task(db, task_id, user.tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(task, field, value)
    if updates.get("status") == "done" and task.completed_at is None:
        task.completed_at = datetime.now(UTC)
    elif updates.get("status") and updates["status"] != "done":
        task.completed_at = None
    await db.flush()
    await db.refresh(task)
    return task