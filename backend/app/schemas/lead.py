import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LeadCreate(BaseModel):
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    score: int | None = Field(None, ge=0, le=100)
    status: str = Field(default="new", max_length=50)
    qualification_reason: str | None = None


class LeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    score: int | None
    status: str
    qualification_reason: str | None
    created_at: datetime
    updated_at: datetime
