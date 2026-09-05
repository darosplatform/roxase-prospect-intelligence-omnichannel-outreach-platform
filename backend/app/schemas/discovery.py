import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.discovery import SOURCE_TYPES


class DiscoveryJobCreate(BaseModel):
    source_type: str = Field(default="url", pattern="|".join(SOURCE_TYPES))
    target: str = Field(..., min_length=1, max_length=2000)
    requested_by: uuid.UUID | None = None
    options: dict | None = None


class DiscoveryJobUpdate(BaseModel):
    status: str | None = None
    options: dict | None = None


class DiscoveryJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    status: str
    source_type: str
    target: str
    target_hash: str
    requested_by: uuid.UUID | None
    options: dict | None
    attempt_count: int
    last_error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DiscoverySourceCreate(BaseModel):
    url: str = Field(..., min_length=1, max_length=4000)
    source_name: str | None = Field(None, max_length=255)
    discovered_via: str | None = Field(None, max_length=255)


class DiscoverySourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    job_id: uuid.UUID
    url: str
    url_hash: str
    status: str
    source_name: str | None
    discovered_via: str | None
    validation_status: str | None
    rejection_reason: str | None
    fetched_at: datetime | None
    http_status: int | None
    content_hash: str | None
    raw_size: int | None
    created_at: datetime
    updated_at: datetime


class RawDocumentCreate(BaseModel):
    source_id: uuid.UUID
    job_id: uuid.UUID
    fetch_url: str
    content_type: str | None = None
    content_body: str | None = None
    size_bytes: int | None = None
    http_status: int | None = None


class ExtractionResultRead(BaseModel):
    company_id: uuid.UUID | None
    contact_ids: list[uuid.UUID]
    evidence_id: uuid.UUID | None
    page_type: str
    skipped_reason: str | None = None


class RawDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    source_id: uuid.UUID
    job_id: uuid.UUID
    fetch_url: str
    content_type: str | None
    content_hash: str
    size_bytes: int | None
    http_status: int | None
    fetched_at: datetime
    confidence: float
    created_at: datetime