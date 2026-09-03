import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

EVIDENCE_TYPES = (
    "company_profile",
    "leadership",
    "hiring",
    "funding",
    "product",
    "partnership",
    "expansion",
    "technology",
    "certification",
    "acquisition",
    "news",
    "job_posting",
    "website",
    "social_business",
    "other",
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Evidence(Base):
    """A piece of observed data collected from a source.

    Answers WHAT (title/excerpt/type), WHERE (source_url), WHEN
    (collected_at/published_at), FROM WHICH SOURCE (source_name) and
    FOR WHICH ENTITY (company_id/contact_id/lead_id).
    """

    __tablename__ = "evidence"
    __table_args__ = (
        Index("ix_evidence_tenant_company", "tenant_id", "company_id"),
        Index("ix_evidence_tenant_contact", "tenant_id", "contact_id"),
        Index("ix_evidence_tenant_lead", "tenant_id", "lead_id"),
        Index("ix_evidence_tenant_type", "tenant_id", "evidence_type"),
        Index("ix_evidence_tenant_hash", "tenant_id", "content_hash"),
        Index("ix_evidence_tenant_collected", "tenant_id", "collected_at"),
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
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL", name="fk_evidence_lead_id"),
        nullable=True,
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    evidence_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )