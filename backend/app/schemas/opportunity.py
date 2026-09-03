import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.opportunity import OPPORTUNITY_STAGES


class OpportunityCreate(BaseModel):
    company_id: uuid.UUID
    contact_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    name: str = Field(..., max_length=500)
    description: str | None = None
    stage: str = Field(default="new", pattern="^(" + "|".join(OPPORTUNITY_STAGES) + ")$")
    value: float | None = Field(None, ge=0)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    probability: float = Field(default=0.0, ge=0.0, le=1.0)
    expected_close_at: date | None = None
    owner_user_id: uuid.UUID | None = None


class OpportunityUpdate(BaseModel):
    name: str | None = Field(None, max_length=500)
    description: str | None = None
    stage: str | None = Field(None, pattern="^(" + "|".join(OPPORTUNITY_STAGES) + ")$")
    value: float | None = Field(None, ge=0)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    probability: float | None = Field(None, ge=0.0, le=1.0)
    expected_close_at: date | None = None
    owner_user_id: uuid.UUID | None = None


class OpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    contact_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    name: str
    description: str | None
    stage: str
    value: float | None
    currency: str | None
    probability: float
    expected_close_at: date | None
    owner_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime