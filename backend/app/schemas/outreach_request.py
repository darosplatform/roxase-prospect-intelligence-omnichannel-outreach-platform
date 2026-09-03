import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.campaign import CAMPAIGN_CHANNELS
from app.models.outreach_request import OUTREACH_STATUSES

_CHANNEL_PATTERN = "^(?:" + "|".join(CAMPAIGN_CHANNELS) + ")$"
_STATUS_PATTERN = "^(?:" + "|".join(OUTREACH_STATUSES) + ")$"


class OutreachRequestCreate(BaseModel):
    campaign_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    channel: str = Field(..., pattern=_CHANNEL_PATTERN)
    template_id: uuid.UUID | None = None
    scheduled_at: datetime | None = None
    logical_send_id: str = Field(default="default", max_length=255)


class OutreachRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    campaign_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    template_id: uuid.UUID | None
    policy_decision_id: uuid.UUID | None
    channel: str
    status: str
    idempotency_key: str
    scheduled_at: datetime | None
    sent_at: datetime | None
    provider_message_id: str | None
    created_at: datetime
    updated_at: datetime