"""Resource demand: a consumer's structured requirement for secondary material."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import (
    DataSource,
    DemandFrequency,
    DemandStatus,
    MaterialCategory,
    MaterialUnit,
    enum_column_type,
)

if TYPE_CHECKING:
    from app.db.models.organization import Organization
    from app.db.models.opportunity import RecoveryOpportunity


class ResourceDemand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """What a facility can absorb, under which engineering constraints.

    The demand row is the deterministic contract the compatibility engine
    checks a supply stream against.
    """

    __tablename__ = "resource_demands"
    __table_args__ = (
        CheckConstraint("min_quantity > 0", name="min_quantity_positive"),
        CheckConstraint(
            "max_quantity IS NULL OR max_quantity >= min_quantity",
            name="max_quantity_not_below_min",
        ),
        CheckConstraint(
            "max_distance_km IS NULL OR max_distance_km > 0", name="max_distance_positive"
        ),
        CheckConstraint(
            "needed_until IS NULL OR needed_from IS NULL OR needed_until >= needed_from",
            name="needed_window_valid",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    category: Mapped[MaterialCategory] = mapped_column(
        enum_column_type(MaterialCategory), nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text)

    # Thresholds consumed by the deterministic compatibility rules.
    min_purity_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    max_moisture_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    max_contamination_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    prohibited_hazards: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    min_quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    max_quantity: Mapped[float | None] = mapped_column(Numeric(14, 3))
    unit: Mapped[MaterialUnit] = mapped_column(enum_column_type(MaterialUnit), nullable=False)
    frequency: Mapped[DemandFrequency] = mapped_column(
        enum_column_type(DemandFrequency),
        nullable=False,
        default=DemandFrequency.CONTINUOUS,
    )

    max_distance_km: Mapped[float | None] = mapped_column(Numeric(8, 1))
    needed_from: Mapped[date | None] = mapped_column(Date)
    needed_until: Mapped[date | None] = mapped_column(Date)
    max_price_per_unit: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")

    status: Mapped[DemandStatus] = mapped_column(
        enum_column_type(DemandStatus), nullable=False, default=DemandStatus.OPEN, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    data_source: Mapped[DataSource] = mapped_column(
        enum_column_type(DataSource), nullable=False, default=DataSource.FORM
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    organization: Mapped["Organization"] = relationship(back_populates="demands")
    opportunities: Mapped[list["RecoveryOpportunity"]] = relationship(
        back_populates="demand", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ResourceDemand {self.title}>"
