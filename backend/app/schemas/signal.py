import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.signal import SIGNAL_TYPES


class SignalCreate(BaseModel):
    company_id: uuid.UUID
    signal_type: str = Field(..., pattern="^(" + "|".join(SIGNAL_TYPES) + ")$")
    title: str | None = Field(None, max_length=500)
    description: str | None = None
    source_url: str | None = None
    source_name: str | None = Field(None, max_length=255)
    detected_at: datetime | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: str = Field(default="active", max_length=50)


class SignalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    signal_type: str
    title: str | None
    description: str | None
    source_url: str | None
    source_name: str | None
    detected_at: datetime
    confidence: float
    status: str
    created_at: datetime
    updated_at: datetime