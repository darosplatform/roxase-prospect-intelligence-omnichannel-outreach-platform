import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Consent / legal basis context. Never asserts full legal compliance — it only
# preserves the authorization context a configurable policy can rely on.
CONSENT_BASIS = ("consent", "legitimate_interest", "contract", "user_initiated", "other", "unknown")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DoNotContact(Base):
    """A central opt-out / suppression rule with absolute priority."""

    __tablename__ = "do_not_contacts"
    __table_args__ = (
        Index("ix_dnc_tenant_contact", "tenant_id", "contact_id"),
        Index("ix_dnc_tenant_company", "tenant_id", "company_id"),
        Index("ix_dnc_tenant_channel", "tenant_id", "channel"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL", name="fk_dnc_contact_id"),
        nullable=True,
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL", name="fk_dnc_company_id"),
        nullable=True,
    )
    channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_dnc_created_by"),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Consent(Base):
    """Optional recorded consent / legal basis context for a contact."""

    __tablename__ = "consents"
    __table_args__ = (
        Index("ix_consents_tenant_contact", "tenant_id", "contact_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL", name="fk_consents_contact_id"),
        nullable=True,
    )
    channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    basis: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_consents_created_by"),
        nullable=True,
    )