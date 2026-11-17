"""Recovery opportunity: a deterministic supply/demand match under evaluation."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    JSON,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import (
    CompatibilityStatus,
    MaterialUnit,
    OpportunityStatus,
    enum_column_type,
)

if TYPE_CHECKING:
    from app.db.models.demand import ResourceDemand
    from app.db.models.material import Material
    from app.db.models.organization import Organization
    from app.db.models.proposal import RecoveryProposal


class RecoveryOpportunity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A candidate symbiosis link produced by the deterministic discovery pass.

    ``compatibility_rules`` stores the evidence trail: one entry per rule that
    was evaluated, so the score is always explainable and reproducible.
    """

    __tablename__ = "recovery_opportunities"
    __table_args__ = (
        # Naming convention generates uq_recovery_opportunities_material_id_resource_demand_id
        UniqueConstraint("material_id", "resource_demand_id"),
        CheckConstraint("compatibility_score >= 0 AND compatibility_score <= 100", name="score_range"),
        CheckConstraint(
            "supplier_organization_id <> consumer_organization_id",
            name="distinct_parties",
        ),
        CheckConstraint("match_quantity > 0", name="match_quantity_positive"),
    )

    material_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_demand_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resource_demands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consumer_organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    compatibility_status: Mapped[CompatibilityStatus] = mapped_column(
        enum_column_type(CompatibilityStatus), nullable=False, index=True
    )
    compatibility_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    compatibility_rules: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    score_breakdown: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    match_quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit: Mapped[MaterialUnit] = mapped_column(enum_column_type(MaterialUnit), nullable=False)
    distance_km: Mapped[float | None] = mapped_column(Numeric(8, 1))
    transport_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    status: Mapped[OpportunityStatus] = mapped_column(
        enum_column_type(OpportunityStatus),
        nullable=False,
        default=OpportunityStatus.IDENTIFIED,
        index=True,
    )
    discovery_method: Mapped[str] = mapped_column(
        String(64), nullable=False, default="deterministic_rule_match"
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    material: Mapped["Material"] = relationship()
    demand: Mapped["ResourceDemand"] = relationship(back_populates="opportunities")
    supplier: Mapped["Organization"] = relationship(
        back_populates="supplied_opportunities",
        foreign_keys=[supplier_organization_id],
    )
    consumer: Mapped["Organization"] = relationship(
        back_populates="demanded_opportunities",
        foreign_keys=[consumer_organization_id],
    )
    proposals: Mapped[list["RecoveryProposal"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<RecoveryOpportunity {self.compatibility_status} score={self.compatibility_score}>"
