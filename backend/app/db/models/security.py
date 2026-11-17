"""Batch 13 operational-security state.

Only additive state lives here:

* a portable fixed-window counter used by every worker, replacing the
  process-local limiter for authentication and MFA decisions;
* archive metadata for bounded audit exports.  Archive rows describe an
  external file by hash; they never contain the file's contents.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SecurityRateLimit(Base):
    """One fixed-window counter (key = account + operation + context)."""

    __tablename__ = "security_rate_limits"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
    )

    bucket_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    window_started_at: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at_epoch: Mapped[int] = mapped_column(Integer, nullable=False)


class AuditArchiveBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Evidence that an audit range was copied to an external archive file."""

    __tablename__ = "audit_archive_batches"

    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    created_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    first_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False, default="jsonl")
