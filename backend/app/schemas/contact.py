import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ContactCreate(BaseModel):
    company_id: uuid.UUID | None = None
    first_name: str | None = Field(None, max_length=255)
    last_name: str | None = Field(None, max_length=255)
    job_title: str | None = Field(None, max_length=500)
    email: str | None = Field(None, max_length=320)
    phone: str | None = Field(None, max_length=50)
    linkedin_url: str | None = Field(None, max_length=500)
    source: str | None = Field(None, max_length=255)


class ContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID | None
    first_name: str | None
    last_name: str | None
    job_title: str | None
    email: str | None
    phone: str | None
    linkedin_url: str | None
    source: str | None
    created_at: datetime
    updated_at: datetime
