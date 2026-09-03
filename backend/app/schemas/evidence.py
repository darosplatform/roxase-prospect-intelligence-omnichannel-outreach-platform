import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.evidence import EVIDENCE_TYPES

_EVIDENCE_TYPE_PATTERN = "^(?:" + "|".join(EVIDENCE_TYPES) + ")$"


class EvidenceCreate(BaseModel):
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    source_url: str = Field(..., min_length=1)
    source_name: str | None = Field(None, max_length=255)
    evidence_type: str | None = Field(None, pattern=_EVIDENCE_TYPE_PATTERN)
    title: str | None = Field(None, max_length=500)
    excerpt: str | None = None
    content_hash: str | None = Field(None, max_length=128)
    collected_at: datetime | None = None
    published_at: datetime | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict | None = None


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    source_url: str
    source_name: str | None
    evidence_type: str | None
    title: str | None
    excerpt: str | None
    content_hash: str | None
    collected_at: datetime
    published_at: datetime | None
    confidence: float
    metadata: dict | None = Field(default=None, validation_alias="evidence_metadata")
    created_at: datetime