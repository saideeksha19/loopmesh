"""Organization: an industrial actor that generates or consumes resources."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import (
    DataSource,
    OrganizationSector,
    OrganizationStatus,
    enum_column_type,
)

if TYPE_CHECKING:
    from app.db.models.demand import ResourceDemand
    from app.db.models.material import Material
    from app.db.models.opportunity import RecoveryOpportunity


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A company participating in the industrial symbiosis network."""

    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="latitude_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="longitude_range",
        ),
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    sector: Mapped[OrganizationSector] = mapped_column(
        enum_column_type(OrganizationSector), nullable=False, index=True
    )

    # Tenant lifecycle. Only platform administration may change this; the
    # organisation workspace has no write path to it. A suspended tenant keeps
    # every row it owns, but disappears from login, organisation switching and
    # request authentication until it is reactivated.
    status: Mapped[OrganizationStatus] = mapped_column(
        enum_column_type(OrganizationStatus),
        nullable=False,
        default=OrganizationStatus.ACTIVE,
        index=True,
    )
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    country: Mapped[str] = mapped_column(String(64), nullable=False)
    region: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(120))
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6))

    contact_name: Mapped[str | None] = mapped_column(String(120))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    description: Mapped[str | None] = mapped_column(Text)

    # Provenance: demo rows are never presented as verified real-world data.
    data_source: Mapped[DataSource] = mapped_column(
        enum_column_type(DataSource), nullable=False, default=DataSource.FORM
    )
    is_demo: Mapped[bool] = mapped_column(nullable=False, default=False)

    materials: Mapped[list["Material"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    demands: Mapped[list["ResourceDemand"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    supplied_opportunities: Mapped[list["RecoveryOpportunity"]] = relationship(
        back_populates="supplier",
        foreign_keys="RecoveryOpportunity.supplier_organization_id",
    )
    demanded_opportunities: Mapped[list["RecoveryOpportunity"]] = relationship(
        back_populates="consumer",
        foreign_keys="RecoveryOpportunity.consumer_organization_id",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Organization {self.slug}>"
