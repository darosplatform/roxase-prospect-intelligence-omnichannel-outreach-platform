import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PolicyEvaluateRequest(BaseModel):
    lead_id: uuid.UUID
    campaign_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    channel: str = Field(..., min_length=1)
    logical_send_id: str = Field(default="default", max_length=255)


class PolicyReason(BaseModel):
    code: str
    message: str
    severity: str


class PolicyEvaluateResponse(BaseModel):
    decision: str
    policy_version: str
    reasons: list[PolicyReason]
    score: int | None
    evidence_ids: list[str] = Field(default_factory=list)
    evaluated_at: datetime
    lead_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    channel: str | None = None
    decision_id: uuid.UUID | None = None


class PolicyDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    lead_id: uuid.UUID | None
    campaign_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    decision: str
    policy_version: str
    channel: str | None
    score: int | None
    reasons: list[dict] | None
    evidence_ids: list[str] | None
    created_at: datetime