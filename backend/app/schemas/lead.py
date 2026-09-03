import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.lead import QUALIFICATION_STATUSES

_QUALIFICATION_PATTERN = "^(?:" + "|".join(QUALIFICATION_STATUSES) + ")$"


class LeadCreate(BaseModel):
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    score: int | None = Field(None, ge=0, le=100)
    status: str = Field(default="new", max_length=50)
    qualification_reason: str | None = None


class LeadUpdate(BaseModel):
    status: str | None = Field(None, max_length=50)
    qualification_reason: str | None = None


class LeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    score: int | None
    status: str
    qualification_reason: str | None
    qualification_status: str
    qualified_at: datetime | None
    qualified_by: uuid.UUID | None
    fit_score: float | None
    intent_score: float | None
    signal_score: float | None
    data_confidence: float | None
    freshness_score: float | None
    scoring_version: str | None
    score_explanation: dict | None
    created_at: datetime
    updated_at: datetime


class LeadQualify(BaseModel):
    status: str = Field(..., pattern=_QUALIFICATION_PATTERN)
    reason: str | None = None
    evidence_ids: list[uuid.UUID] = Field(default_factory=list)


class ScoreFactor(BaseModel):
    name: str
    impact: float
    evidence_ids: list[uuid.UUID] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    fit: float
    intent: float
    signal: float
    data_confidence: float
    freshness: float


class LeadScoreRead(BaseModel):
    score: int
    scoring_version: str
    breakdown: ScoreBreakdown
    factors: list[ScoreFactor]
    computed_at: datetime