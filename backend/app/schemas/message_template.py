import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.campaign import CAMPAIGN_CHANNELS

_CHANNEL_PATTERN = "^(?:" + "|".join(CAMPAIGN_CHANNELS) + ")$"


class MessageTemplateCreate(BaseModel):
    name: str = Field(..., max_length=255)
    channel: str = Field(..., pattern=_CHANNEL_PATTERN)
    subject: str | None = Field(None, max_length=500)
    body: str = Field(..., min_length=1)
    is_active: bool = True


class MessageTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    channel: str
    subject: str | None
    body: str
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime