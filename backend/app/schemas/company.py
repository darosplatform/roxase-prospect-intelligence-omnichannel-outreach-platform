import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    legal_name: str = Field(..., max_length=500)
    domain: str | None = Field(None, max_length=255)
    country: str | None = Field(None, max_length=2)
    industry: str | None = Field(None, max_length=255)
    employee_count: int | None = Field(None, ge=0)
    source: str | None = Field(None, max_length=255)


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    legal_name: str
    domain: str | None
    country: str | None
    industry: str | None
    employee_count: int | None
    source: str | None
    created_at: datetime
    updated_at: datetime
