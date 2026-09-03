import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

ROLES = ("owner", "admin", "manager", "analyst", "operator", "viewer")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (
        {"comment": "Maps users to workspaces with a role per workspace"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="viewer")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="members")  # noqa: F821
    user: Mapped["User"] = relationship(back_populates="workspace_memberships")  # noqa: F821
