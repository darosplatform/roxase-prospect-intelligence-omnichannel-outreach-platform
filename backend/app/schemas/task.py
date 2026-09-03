import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TASK_PRIORITIES, TASK_STATUSES


class TaskCreate(BaseModel):
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    assigned_to: uuid.UUID | None = None
    title: str = Field(..., max_length=500)
    description: str | None = None
    status: str = Field(default="todo", pattern="^(" + "|".join(TASK_STATUSES) + ")$")
    priority: str = Field(default="medium", pattern="^(" + "|".join(TASK_PRIORITIES) + ")$")
    due_at: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(None, max_length=500)
    description: str | None = None
    status: str | None = Field(None, pattern="^(" + "|".join(TASK_STATUSES) + ")$")
    priority: str | None = Field(None, pattern="^(" + "|".join(TASK_PRIORITIES) + ")$")
    due_at: datetime | None = None
    assigned_to: uuid.UUID | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    opportunity_id: uuid.UUID | None
    assigned_to: uuid.UUID | None
    title: str
    description: str | None
    status: str
    priority: str
    due_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime