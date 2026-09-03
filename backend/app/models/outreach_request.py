import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

OUTREACH_STATUSES = (
    "pending",
    "approved",
    "denied",
    "queued",
    "dispatching",
    "sent",
    "delivered",
    "failed",
    "cancelled",
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class OutreachRequest(Base):
    """An intention to send a message, decoupled from any provider.

    Flow: pending -> approved -> queued -> dispatching -> sent/delivered/failed.
    Denied requests never reach a provider.
    """

    __tablename__ = "outreach_requests"
    __table_args__ = (
        Index("ix_outreach_tenant_status", "tenant_id", "status"),
        Index("ix_outreach_tenant_lead", "tenant_id", "lead_id"),
        Index("uq_outreach_tenant_idempotency", "tenant_id", "idempotency_key", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL", name="fk_outreach_campaign_id"),
        nullable=True,
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL", name="fk_outreach_lead_id"),
        nullable=True,
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL", name="fk_outreach_contact_id"),
        nullable=True,
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("message_templates.id", ondelete="SET NULL", name="fk_outreach_template_id"),
        nullable=True,
    )
    policy_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "policy_decisions.id",
            ondelete="SET NULL",
            name="fk_outreach_policy_decision_id",
        ),
        nullable=True,
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )