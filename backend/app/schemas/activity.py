import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.activity import ACTIVITY_TYPES


class ActivityCreate(BaseModel):
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    activity_type: str = Field(..., pattern="^(" + "|".join(ACTIVITY_TYPES) + ")$")
    subject: str | None = Field(None, max_length=500)
    description: str | None = None
    occurred_at: datetime | None = None


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    opportunity_id: uuid.UUID | None
    user_id: uuid.UUID | None
    activity_type: str
    subject: str | None
    description: str | None
    occurred_at: datetime
    created_at: datetime