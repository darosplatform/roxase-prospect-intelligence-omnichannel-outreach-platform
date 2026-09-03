import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.campaign import CAMPAIGN_CHANNELS, CAMPAIGN_STATUSES


class CampaignPolicy(BaseModel):
    min_lead_score: int | None = Field(None, ge=0, le=100)
    min_confidence: float | None = Field(None, ge=0.0, le=1.0)
    min_evidence_freshness_days: int | None = Field(None, ge=0)
    allowed_channels: list[str] | None = None
    require_qualification: bool = False
    require_evidence: bool = False
    max_contact_per_day: int | None = Field(None, ge=1)
    dry_run: bool = True


class CampaignCreate(BaseModel):
    name: str = Field(..., max_length=500)
    description: str | None = None
    status: str = Field(default="draft", pattern="^(" + "|".join(CAMPAIGN_STATUSES) + ")$")
    channel: str = Field(default="email", pattern="^(" + "|".join(CAMPAIGN_CHANNELS) + ")$")
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    policy: CampaignPolicy | None = None


class CampaignUpdate(BaseModel):
    name: str | None = Field(None, max_length=500)
    description: str | None = None
    status: str | None = Field(None, pattern="^(" + "|".join(CAMPAIGN_STATUSES) + ")$")
    channel: str | None = Field(None, pattern="^(" + "|".join(CAMPAIGN_CHANNELS) + ")$")
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    policy: CampaignPolicy | None = None


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
    policy: dict | None = None
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime