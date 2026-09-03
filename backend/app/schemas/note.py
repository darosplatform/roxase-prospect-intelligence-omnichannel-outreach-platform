import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NoteCreate(BaseModel):
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    content: str = Field(..., min_length=1)


class NoteUpdate(BaseModel):
    content: str | None = Field(None, min_length=1)


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    opportunity_id: uuid.UUID | None
    author_user_id: uuid.UUID
    content: str
    created_at: datetime
    updated_at: datetime