import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

POLICY_DECISIONS = ("ALLOW", "DENY", "REVIEW")
POLICY_VERSION = "v1"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PolicyDecision(Base):
    """The persisted result of a policy evaluation, kept for traceability."""

    __tablename__ = "policy_decisions"
    __table_args__ = (
        Index("ix_policy_tenant_lead", "tenant_id", "lead_id"),
        Index("ix_policy_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL", name="fk_policy_decisions_lead_id"),
        nullable=True,
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL", name="fk_policy_decisions_campaign_id"),
        nullable=True,
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL", name="fk_policy_decisions_contact_id"),
        nullable=True,
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False, default=POLICY_VERSION)
    channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasons: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    evidence_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_policy_decisions_created_by"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )