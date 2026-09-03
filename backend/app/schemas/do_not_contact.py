import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.campaign import CAMPAIGN_CHANNELS
from app.models.do_not_contact import CONSENT_BASIS

_CHANNEL_PATTERN = "^(?:" + "|".join(CAMPAIGN_CHANNELS) + ")$"
_BASIS_PATTERN = "^(?:" + "|".join(CONSENT_BASIS) + ")$"


class DoNotContactCreate(BaseModel):
    contact_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    channel: str | None = Field(None, pattern=_CHANNEL_PATTERN)
    reason: str | None = None
    source: str | None = None
    expires_at: datetime | None = None


class DoNotContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: uuid.UUID | None
    company_id: uuid.UUID | None
    channel: str | None
    reason: str | None
    source: str | None
    expires_at: datetime | None
    created_at: datetime


class ConsentCreate(BaseModel):
    contact_id: uuid.UUID
    channel: str | None = Field(None, pattern=_CHANNEL_PATTERN)
    basis: str = Field(default="unknown", pattern=_BASIS_PATTERN)


class ConsentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: uuid.UUID | None
    channel: str | None
    basis: str
    recorded_at: datetime