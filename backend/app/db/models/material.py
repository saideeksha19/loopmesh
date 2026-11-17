"""Material streams and their structured technical specifications."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import (
    DataSource,
    MaterialCategory,
    MaterialCondition,
    MaterialStatus,
    MaterialUnit,
    enum_column_type,
)

if TYPE_CHECKING:
    from app.db.models.organization import Organization


class Material(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A byproduct stream offered by a supplying organization.

    This is the "Material DNA" record: a structured, form/CSV/document derived
    profile. No computer vision or image inference is involved anywhere.
    """

    __tablename__ = "materials"
    __table_args__ = (
        CheckConstraint("quantity_available > 0", name="quantity_positive"),
        CheckConstraint(
            "availability_end IS NULL OR availability_start IS NULL "
            "OR availability_end >= availability_start",
            name="availability_window_valid",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reference_code: Mapped[str] = mapped_column(String(48), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[MaterialCategory] = mapped_column(
        enum_column_type(MaterialCategory), nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text)

    quantity_available: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit: Mapped[MaterialUnit] = mapped_column(
        enum_column_type(MaterialUnit), nullable=False, default=MaterialUnit.TONNE
    )
    condition: Mapped[MaterialCondition] = mapped_column(
        enum_column_type(MaterialCondition),
        nullable=False,
        default=MaterialCondition.AS_GENERATED,
    )
    status: Mapped[MaterialStatus] = mapped_column(
        enum_column_type(MaterialStatus),
        nullable=False,
        default=MaterialStatus.AVAILABLE,
        index=True,
    )

    hazard_class: Mapped[str | None] = mapped_column(String(40))
    handling_requirements: Mapped[str | None] = mapped_column(Text)
    origin_process: Mapped[str | None] = mapped_column(String(160))

    availability_start: Mapped[date | None] = mapped_column(Date)
    availability_end: Mapped[date | None] = mapped_column(Date)

    data_source: Mapped[DataSource] = mapped_column(
        enum_column_type(DataSource), nullable=False, default=DataSource.FORM
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    organization: Mapped["Organization"] = relationship(back_populates="materials")
    specification: Mapped["MaterialSpecification | None"] = relationship(
        back_populates="material",
        cascade="all, delete-orphan",
        uselist=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Material {self.reference_code}>"


class MaterialSpecification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Measured/declared properties used by the deterministic compatibility rules.

    Percentages are stored as 0-100 values. Optional fields are genuinely
    optional: a missing measurement is treated as *unknown evidence* by the
    compatibility engine, never as a pass.
    """

    __tablename__ = "material_specifications"
    __table_args__ = (
        CheckConstraint(
            "purity_pct IS NULL OR (purity_pct >= 0 AND purity_pct <= 100)",
            name="purity_range",
        ),
        CheckConstraint(
            "moisture_pct IS NULL OR (moisture_pct >= 0 AND moisture_pct <= 100)",
            name="moisture_range",
        ),
        CheckConstraint(
            "contamination_pct IS NULL OR (contamination_pct >= 0 AND contamination_pct <= 100)",
            name="contamination_range",
        ),
        CheckConstraint("ph_value IS NULL OR (ph_value >= 0 AND ph_value <= 14)", name="ph_range"),
        CheckConstraint(
            "particle_size_mm IS NULL OR particle_size_mm > 0", name="particle_size_positive"
        ),
    )

    material_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    purity_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    moisture_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    contamination_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    ph_value: Mapped[float | None] = mapped_column(Numeric(4, 2))
    particle_size_mm: Mapped[float | None] = mapped_column(Numeric(10, 2))
    calorific_value_mj_kg: Mapped[float | None] = mapped_column(Numeric(6, 2))

    # e.g. [{"substance": "SiO2", "pct": 38.0}, ...]
    composition: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # e.g. {"Pb": 0.4, "Cl": 1.1} expressed in percent
    contaminants: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    assay_method: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)

    material: Mapped["Material"] = relationship(back_populates="specification")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<MaterialSpecification material={self.material_id}>"
