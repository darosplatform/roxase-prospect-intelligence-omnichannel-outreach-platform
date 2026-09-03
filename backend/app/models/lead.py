import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

QUALIFICATION_STATUSES = ("unqualified", "candidate", "qualified", "disqualified")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_tenant_company", "tenant_id", "company_id"),
        Index("ix_leads_tenant_contact", "tenant_id", "contact_id"),
        Index("ix_leads_tenant_qualification", "tenant_id", "qualification_status"),
        Index("ix_leads_tenant_score", "tenant_id", "score"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="new", index=True
    )
    qualification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualification_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unqualified", index=True
    )
    qualified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    qualified_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id", ondelete="SET NULL", name="fk_leads_qualified_by"
        ),
        nullable=True,
    )
    fit_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    intent_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    freshness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    scoring_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    score_explanation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )