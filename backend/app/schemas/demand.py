"""Resource demand schemas."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import ConfigDict

from app.db.enums import DemandFrequency, DemandStatus, MaterialCategory, MaterialUnit
from app.schemas.common import ApiModel
from app.schemas.organization import OrganizationSummary


class ResourceDemandRead(ApiModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None = None
    category: MaterialCategory
    organization: OrganizationSummary
    min_purity_pct: float | None = None
    max_moisture_pct: float | None = None
    max_contamination_pct: float | None = None
    prohibited_hazards: list[str] = []
    min_quantity: float
    max_quantity: float | None = None
    unit: MaterialUnit
    frequency: DemandFrequency
    max_distance_km: float | None = None
    needed_from: date | None = None
    needed_until: date | None = None
    max_price_per_unit: float | None = None
    currency: str
    status: DemandStatus
    is_demo: bool
    created_at: datetime
