import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.campaign import CAMPAIGN_CHANNELS, CAMPAIGN_STATUSES


class CampaignCreate(BaseModel):
    name: str = Field(..., max_length=500)
    description: str | None = None
    status: str = Field(default="draft", pattern="^(" + "|".join(CAMPAIGN_STATUSES) + ")$")
    channel: str = Field(default="email", pattern="^(" + "|".join(CAMPAIGN_CHANNELS) + ")$")
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class CampaignUpdate(BaseModel):
    name: str | None = Field(None, max_length=500)
    description: str | None = None
    status: str | None = Field(None, pattern="^(" + "|".join(CAMPAIGN_STATUSES) + ")$")
    channel: str | None = Field(None, pattern="^(" + "|".join(CAMPAIGN_CHANNELS) + ")$")
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class CampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str | None
    status: str
    channel: str
    created_by: uuid.UUID | None
    starts_at: datetime | None
    ends_at: datetime | None
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime