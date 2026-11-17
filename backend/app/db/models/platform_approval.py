"""Two-person approval requests for high-impact platform operations.

An approval is a first-class record, not a flag on the organisation: it names
the exact tenant, action and reason, and records who asked, who decided and who
executed. There is no update endpoint — changing the target, action or reason
means creating a new request, which is what makes an approval bound to a
specific operation.

Only a *pending* request can be approved or rejected, only an *approved* request
can be executed, and every terminal state is final.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import ApprovalAction, ApprovalStatus, enum_column_type


class PlatformApprovalRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platform_approval_requests"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        CheckConstraint(
            "decided_at IS NULL OR decided_at >= created_at",
            name="decision_after_creation",
        ),
        CheckConstraint(
            "executed_at IS NULL OR executed_at >= created_at",
            name="execution_after_creation",
        ),
        Index(
            "ix_platform_approvals_status_expiry",
            "status",
            "expires_at",
        ),
        Index(
            "ix_platform_approvals_organization_status",
            "organization_id",
            "status",
        ),
        Index(
            "ix_platform_approvals_requester",
            "requested_by_user_id",
            "created_at",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[ApprovalAction] = mapped_column(
        enum_column_type(ApprovalAction), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ApprovalStatus] = mapped_column(
        enum_column_type(ApprovalStatus),
        nullable=False,
        default=ApprovalStatus.PENDING,
        index=True,
    )

    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)

    executed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Incremented under the row lock when several operators race to execute the
    # same approved request. It is a diagnostic, never the concurrency control.
    execution_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<PlatformApproval {self.id} {self.action.value} {self.status.value}>"
