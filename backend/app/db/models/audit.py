"""Immutable audit trail for material, proposal and ledger mutations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit_integrity import GENESIS_HASH
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.db.enums import AuditSeverity, enum_column_type


class AuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single journal entry describing who changed what, from which state, and why.

    Rows are append-only by application contract: no API endpoint updates or
    deletes them. Batch 13 adds a hash chain so out-of-band edits are evident.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        UniqueConstraint("integrity_sequence", name="uq_audit_events_integrity_sequence"),
    )

    # Batch 13 chained integrity.  Nullable only so an insert can be flushed to
    # obtain its database default before the chain row is locked and sealed.
    integrity_sequence: Mapped[int | None] = mapped_column(BigInteger, index=True)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    event_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)

    previous_state: Mapped[str | None] = mapped_column(String(32))
    new_state: Mapped[str | None] = mapped_column(String(32))

    actor: Mapped[str] = mapped_column(String(120), nullable=False, default="system")
    actor_id: Mapped[str | None] = mapped_column(String(120), index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )

    severity: Mapped[AuditSeverity] = mapped_column(
        enum_column_type(AuditSeverity), nullable=False, default=AuditSeverity.INFO
    )
    summary: Mapped[str] = mapped_column(String(400), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AuditEvent {self.event_type}>"


class AuditIntegrityState(Base):
    """Single-row chain head, locked while appending in PostgreSQL."""

    __tablename__ = "audit_integrity_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, default=GENESIS_HASH
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
