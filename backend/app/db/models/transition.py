"""Append-only lifecycle transition history.

Every state change of a proposal or transaction is recorded here, independent of
the wider audit journal. Rows are never updated or deleted by the API.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, JSON, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.db.enums import ActorRole, TransitionEntity, enum_column_type

if TYPE_CHECKING:
    from app.db.models.organization import Organization


class StatusTransition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One validated transition of a proposal or transaction."""

    __tablename__ = "status_transitions"
    __table_args__ = (
        Index(
            "ix_status_transitions_entity",
            "entity_type",
            "entity_id",
            "occurred_at",
        ),
    )

    entity_type: Mapped[TransitionEntity] = mapped_column(
        enum_column_type(TransitionEntity), nullable=False, index=True
    )
    # Polymorphic reference: proposals and transactions share this history table.
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)

    action: Mapped[str] = mapped_column(String(32), nullable=False)
    from_state: Mapped[str] = mapped_column(String(32), nullable=False)
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)

    actor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_role: Mapped[ActorRole] = mapped_column(
        enum_column_type(ActorRole), nullable=False
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )

    reason: Mapped[str | None] = mapped_column(Text)
    context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    organization: Mapped["Organization | None"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<StatusTransition {self.entity_type} {self.action} {self.from_state}->{self.to_state}>"
