"""Recovery proposals and the transactions that follow approval.

Lifecycle invariants are enforced twice: by the central state machine in
``app.services.lifecycle`` (which produces meaningful errors and audit records)
and by database ``CHECK`` constraints (which make impossible rows impossible,
even if a future code path forgets a rule).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import (
    CompatibilityStatus,
    MaterialUnit,
    ProposalStatus,
    TransactionStatus,
    VerificationMethod,
    enum_column_type,
)

if TYPE_CHECKING:
    from app.db.models.opportunity import RecoveryOpportunity
    from app.db.models.organization import Organization


class RecoveryProposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A concrete offer to transfer a matched quantity between two parties."""

    __tablename__ = "recovery_proposals"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("price_per_unit IS NULL OR price_per_unit >= 0", name="price_non_negative"),
        CheckConstraint("version >= 0", name="version_non_negative"),
        CheckConstraint(
            "status <> 'approved' OR (approved_at IS NOT NULL AND approved_by IS NOT NULL "
            "AND approval_reference IS NOT NULL)",
            name="approved_requires_authority",
        ),
        CheckConstraint(
            "status NOT IN ('submitted', 'under_review', 'approved', 'in_progress', 'completed') "
            "OR submitted_at IS NOT NULL",
            name="submitted_requires_timestamp",
        ),
        CheckConstraint(
            "status <> 'rejected' OR (rejected_at IS NOT NULL AND rejected_by IS NOT NULL "
            "AND rejection_reason IS NOT NULL)",
            name="rejected_requires_reason",
        ),
        CheckConstraint(
            "status <> 'completed' OR completed_at IS NOT NULL",
            name="completed_requires_timestamp",
        ),
        CheckConstraint(
            "status <> 'failed' OR failure_reason IS NOT NULL",
            name="failed_requires_reason",
        ),
        CheckConstraint(
            "status <> 'cancelled' OR (cancelled_at IS NOT NULL AND cancellation_reason IS NOT NULL)",
            name="cancelled_requires_reason",
        ),
    )

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recovery_opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proposed_by_organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    receiving_organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit: Mapped[MaterialUnit] = mapped_column(enum_column_type(MaterialUnit), nullable=False)
    price_per_unit: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")

    status: Mapped[ProposalStatus] = mapped_column(
        enum_column_type(ProposalStatus),
        nullable=False,
        default=ProposalStatus.DRAFT,
        index=True,
    )
    # Snapshot of the deterministic screening result at proposal time.
    compatibility_status: Mapped[CompatibilityStatus] = mapped_column(
        enum_column_type(CompatibilityStatus),
        nullable=False,
        default=CompatibilityStatus.UNVERIFIED,
    )
    terms: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- lifecycle evidence -------------------------------------------------
    submitted_by: Mapped[str | None] = mapped_column(String(120))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(120))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(120))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_reference: Mapped[str | None] = mapped_column(String(200))
    approval_evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rejected_by: Mapped[str | None] = mapped_column(String(120))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    withdrawn_by: Mapped[str | None] = mapped_column(String(120))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)

    # Optimistic concurrency token, incremented on every transition.
    version: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")

    opportunity: Mapped["RecoveryOpportunity"] = relationship(back_populates="proposals")
    transaction: Mapped["RecoveryTransaction | None"] = relationship(
        back_populates="proposal", cascade="all, delete-orphan", uselist=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<RecoveryProposal {self.status} {self.quantity} {self.unit}>"


class RecoveryTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Physical movement of recovered material and its verification evidence.

    A transaction can only become ``verified`` with a positive verified quantity,
    a verifying actor, a verification timestamp and evidence. Only verified
    transactions contribute to recovered-material totals.
    """

    __tablename__ = "recovery_transactions"
    __table_args__ = (
        CheckConstraint(
            "accepted_quantity IS NULL OR accepted_quantity > 0",
            name="accepted_quantity_positive",
        ),
        CheckConstraint(
            "transferred_quantity IS NULL OR transferred_quantity > 0",
            name="transferred_quantity_positive",
        ),
        CheckConstraint(
            "verified_quantity IS NULL OR verified_quantity > 0",
            name="verified_quantity_positive",
        ),
        CheckConstraint(
            "status <> 'verified' OR (verified_quantity IS NOT NULL AND verified_at IS NOT NULL "
            "AND verified_by IS NOT NULL)",
            name="verified_requires_evidence",
        ),
        CheckConstraint(
            "status <> 'transferred' OR (transferred_quantity IS NOT NULL AND transferred_at IS NOT NULL)",
            name="transferred_requires_quantity",
        ),
        CheckConstraint(
            "status <> 'rejected' OR (rejected_at IS NOT NULL AND rejection_reason IS NOT NULL)",
            name="rejected_requires_reason",
        ),
        CheckConstraint(
            "status <> 'cancelled' OR (cancelled_at IS NOT NULL AND cancellation_reason IS NOT NULL)",
            name="cancelled_requires_reason",
        ),
        CheckConstraint(
            "source_organization_id <> destination_organization_id",
            name="distinct_parties",
        ),
        CheckConstraint(
            "transport_distance_km IS NULL OR transport_distance_km >= 0",
            name="distance_non_negative",
        ),
        CheckConstraint("version >= 0", name="version_non_negative"),
    )

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recovery_proposals.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[TransactionStatus] = mapped_column(
        enum_column_type(TransactionStatus),
        nullable=False,
        default=TransactionStatus.CREATED,
        index=True,
    )

    # Parties are derived from the approved proposal, never from client input.
    source_organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    destination_organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    accepted_quantity: Mapped[float | None] = mapped_column(Numeric(14, 3))
    transferred_quantity: Mapped[float | None] = mapped_column(Numeric(14, 3))
    verified_quantity: Mapped[float | None] = mapped_column(Numeric(14, 3))
    unit: Mapped[MaterialUnit] = mapped_column(enum_column_type(MaterialUnit), nullable=False)

    transport_distance_km: Mapped[float | None] = mapped_column(Numeric(8, 1))
    carrier_name: Mapped[str | None] = mapped_column(String(160))
    transfer_reference: Mapped[str | None] = mapped_column(String(120))
    material_identification: Mapped[str | None] = mapped_column(String(200))

    # --- transfer evidence --------------------------------------------------
    transfer_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transferred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transfer_recorded_by: Mapped[str | None] = mapped_column(String(120))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- verification evidence ----------------------------------------------
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[str | None] = mapped_column(String(120))
    verification_method: Mapped[VerificationMethod | None] = mapped_column(
        enum_column_type(VerificationMethod)
    )
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # --- exception states ---------------------------------------------------
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_by: Mapped[str | None] = mapped_column(String(120))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[str | None] = mapped_column(String(120))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)

    notes: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")

    proposal: Mapped["RecoveryProposal"] = relationship(back_populates="transaction")
    source_organization: Mapped["Organization"] = relationship(
        foreign_keys=[source_organization_id]
    )
    destination_organization: Mapped["Organization"] = relationship(
        foreign_keys=[destination_organization_id]
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<RecoveryTransaction {self.status}>"
